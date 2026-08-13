from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.database import get_db
from app.models.activity import ActivityLog
from app.models.boq import BOQ, BOQStatus
from app.models.cost import CostEstimate
from app.models.document import Document, ProcessingStatus
from app.models.project import Project, ProjectMember, ProjectStatus
from app.models.user import User
from app.schemas.dashboard import AttentionItem, DashboardStats, WeekSnapshot

router = APIRouter()


def _accessible_project_ids(user: User):
    return select(Project.id).where(
        or_(
            Project.owner_id == user.id,
            Project.id.in_(select(ProjectMember.project_id).where(ProjectMember.user_id == user.id)),
        )
    )


@router.get("/stats", response_model=DashboardStats)
def get_dashboard_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DashboardStats:
    project_ids = _accessible_project_ids(current_user)
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    total_projects = db.scalar(select(func.count()).select_from(Project).where(Project.id.in_(project_ids))) or 0
    active_projects = (
        db.scalar(
            select(func.count())
            .select_from(Project)
            .where(Project.id.in_(project_ids), Project.status == ProjectStatus.ACTIVE)
        )
        or 0
    )
    documents_uploaded = (
        db.scalar(select(func.count()).select_from(Document).where(Document.project_id.in_(project_ids))) or 0
    )
    boqs_generated = db.scalar(select(func.count()).select_from(BOQ).where(BOQ.project_id.in_(project_ids))) or 0
    pending_reviews = (
        db.scalar(
            select(func.count())
            .select_from(Project)
            .where(Project.id.in_(project_ids), Project.status == ProjectStatus.IN_REVIEW)
        )
        or 0
    )
    pending_boq_reviews = (
        db.scalar(
            select(func.count())
            .select_from(BOQ)
            .where(BOQ.project_id.in_(project_ids), BOQ.status == BOQStatus.IN_REVIEW)
        )
        or 0
    )

    activities = db.scalars(
        select(ActivityLog)
        .where(or_(ActivityLog.user_id == current_user.id, ActivityLog.project_id.in_(project_ids)))
        .order_by(ActivityLog.created_at.desc())
        .limit(10)
    ).all()
    recent_activity = [
        {
            "id": a.id,
            "action": a.action,
            "message": a.message,
            "project_id": a.project_id,
            "created_at": a.created_at.isoformat(),
        }
        for a in activities
    ]

    # --- This week snapshot ---
    week_docs = (
        db.scalar(
            select(func.count())
            .select_from(Document)
            .where(Document.project_id.in_(project_ids), Document.created_at >= week_ago)
        )
        or 0
    )
    week_boqs = (
        db.scalar(
            select(func.count())
            .select_from(BOQ)
            .where(BOQ.project_id.in_(project_ids), BOQ.created_at >= week_ago)
        )
        or 0
    )
    week_failed = (
        db.scalar(
            select(func.count())
            .select_from(Document)
            .where(
                Document.project_id.in_(project_ids),
                Document.created_at >= week_ago,
                Document.processing_status == ProcessingStatus.FAILED,
            )
        )
        or 0
    )
    week_projects = (
        db.scalar(
            select(func.count(func.distinct(ActivityLog.project_id)))
            .select_from(ActivityLog)
            .where(
                ActivityLog.project_id.in_(project_ids),
                ActivityLog.created_at >= week_ago,
                ActivityLog.project_id.is_not(None),
            )
        )
        or 0
    )

    # --- Needs attention ---
    attention: list[AttentionItem] = []
    project_name_cache: dict[int, str] = {}

    def project_name(pid: int) -> str:
        if pid not in project_name_cache:
            proj = db.get(Project, pid)
            project_name_cache[pid] = proj.name if proj else f"Project {pid}"
        return project_name_cache[pid]

    failed_docs = db.scalars(
        select(Document)
        .where(Document.project_id.in_(project_ids), Document.processing_status == ProcessingStatus.FAILED)
        .order_by(Document.updated_at.desc())
        .limit(8)
    ).all()
    for doc in failed_docs:
        attention.append(
            AttentionItem(
                kind="failed_upload",
                severity="error",
                title=f"Failed file: {doc.original_filename}",
                detail=(doc.error_message or "Processing failed — reopen the project and retry analyze/CAD.")[:180],
                project_id=doc.project_id,
                project_name=project_name(doc.project_id),
                entity_id=doc.id,
                action_label="Fix in project",
            )
        )

    # Projects with documents but no BOQ yet
    projects_with_docs = db.scalars(
        select(Project.id)
        .where(
            Project.id.in_(project_ids),
            Project.id.in_(select(Document.project_id).where(Document.project_id.in_(project_ids))),
            ~Project.id.in_(select(BOQ.project_id).where(BOQ.project_id.in_(project_ids))),
            Project.status != ProjectStatus.ARCHIVED,
        )
        .limit(8)
    ).all()
    for pid in projects_with_docs:
        attention.append(
            AttentionItem(
                kind="missing_boq",
                severity="warning",
                title="BOQ not generated yet",
                detail="This project has uploads but no BOQ. Run Analyze / Process CAD, then Generate BOQ.",
                project_id=pid,
                project_name=project_name(pid),
                action_label="Generate BOQ",
            )
        )

    # Empty BOQs (zero items)
    empty_boqs = db.scalars(
        select(BOQ)
        .options(selectinload(BOQ.items))
        .where(BOQ.project_id.in_(project_ids))
        .order_by(BOQ.updated_at.desc())
        .limit(20)
    ).all()
    empty_added = 0
    for boq in empty_boqs:
        if boq.items:
            continue
        attention.append(
            AttentionItem(
                kind="empty_boq",
                severity="warning",
                title=f"Empty BOQ: {boq.title}",
                detail="BOQ exists but has 0 line items. Re-run CAD/document analysis, then regenerate.",
                project_id=boq.project_id,
                project_name=project_name(boq.project_id),
                entity_id=boq.id,
                action_label="Open BOQ",
            )
        )
        empty_added += 1
        if empty_added >= 5:
            break

    # Pending review projects / BOQs
    review_projects = db.scalars(
        select(Project)
        .where(Project.id.in_(project_ids), Project.status == ProjectStatus.IN_REVIEW)
        .limit(5)
    ).all()
    for proj in review_projects:
        attention.append(
            AttentionItem(
                kind="pending_review",
                severity="info",
                title=f"Project in review: {proj.name}",
                detail="Waiting on engineer review / approval.",
                project_id=proj.id,
                project_name=proj.name,
                action_label="Review",
            )
        )

    review_boqs = db.scalars(
        select(BOQ)
        .where(BOQ.project_id.in_(project_ids), BOQ.status == BOQStatus.IN_REVIEW)
        .order_by(BOQ.updated_at.desc())
        .limit(5)
    ).all()
    for boq in review_boqs:
        attention.append(
            AttentionItem(
                kind="pending_review",
                severity="info",
                title=f"BOQ awaiting review: {boq.title}",
                detail="Submit or approve this BOQ from the project workspace.",
                project_id=boq.project_id,
                project_name=project_name(boq.project_id),
                entity_id=boq.id,
                action_label="Review BOQ",
            )
        )

    # De-dupe by kind+project+title, keep order, cap list
    seen: set[str] = set()
    unique_attention: list[AttentionItem] = []
    for item in attention:
        key = f"{item.kind}:{item.project_id}:{item.title}"
        if key in seen:
            continue
        seen.add(key)
        unique_attention.append(item)
        if len(unique_attention) >= 12:
            break

    return DashboardStats(
        total_projects=total_projects,
        active_projects=active_projects,
        documents_uploaded=documents_uploaded,
        boqs_generated=boqs_generated,
        pending_reviews=pending_reviews + pending_boq_reviews,
        recent_activity=recent_activity,
        needs_attention=unique_attention,
        week=WeekSnapshot(
            documents_uploaded=week_docs,
            boqs_generated=week_boqs,
            projects_touched=week_projects,
            failed_uploads=week_failed,
        ),
    )


def _resolve_since(range_key: str) -> datetime | None:
    now = datetime.now(timezone.utc)
    if range_key == "7d":
        return now - timedelta(days=7)
    if range_key == "30d":
        return now - timedelta(days=30)
    return None


def _build_analytics_snapshot(db: Session, project_ids: list[int], since: datetime | None) -> dict:
    if not project_ids:
        return {
            "materials": [],
            "categories": [],
            "earthwork": {"cut": 0.0, "fill": 0.0, "balance": 0.0, "balance_label": "balanced"},
            "costs": {"total_estimated": 0.0, "by_project": []},
            "pavement": {"GSB": 0.0, "WMM": 0.0, "DBM": 0.0, "Bituminous Concrete": 0.0, "Asphalt": 0.0},
            "meta": {
                "boq_count": 0,
                "estimate_count": 0,
                "project_count": 0,
                "item_count": 0,
                "last_updated": None,
                "has_boqs": False,
                "has_estimates": False,
            },
        }

    boq_stmt = (
        select(BOQ)
        .options(selectinload(BOQ.items))
        .where(BOQ.project_id.in_(project_ids))
        .order_by(BOQ.updated_at.desc())
    )
    if since is not None:
        boq_stmt = boq_stmt.where(BOQ.created_at >= since)
    boqs = db.scalars(boq_stmt).all()

    material_totals: dict[str, float] = {}
    material_units: dict[str, str] = {}
    category_totals: dict[str, float] = {}
    item_count = 0
    last_updated: datetime | None = None

    for boq in boqs:
        if last_updated is None or (boq.updated_at and boq.updated_at > last_updated):
            last_updated = boq.updated_at
        for item in boq.items:
            item_count += 1
            key = item.description
            qty = float(item.quantity)
            material_totals[key] = material_totals.get(key, 0) + qty
            if key not in material_units and item.unit:
                material_units[key] = item.unit
            cat = item.category or "General"
            category_totals[cat] = category_totals.get(cat, 0) + qty
            if item.updated_at and (last_updated is None or item.updated_at > last_updated):
                last_updated = item.updated_at

    est_stmt = select(CostEstimate).where(CostEstimate.project_id.in_(project_ids))
    if since is not None:
        est_stmt = est_stmt.where(CostEstimate.created_at >= since)
    estimates = db.scalars(est_stmt).all()

    cost_total = 0.0
    cost_by_project: dict[int, dict] = {}
    for e in estimates:
        amount = float(e.total_amount)
        cost_total += amount
        if e.created_at and (last_updated is None or e.created_at > last_updated):
            last_updated = e.created_at
        project = db.get(Project, e.project_id)
        name = project.name if project else f"Project {e.project_id}"
        bucket = cost_by_project.setdefault(e.project_id, {"project_id": e.project_id, "name": name, "amount": 0.0})
        bucket["amount"] += amount

    total_qty = sum(material_totals.values()) or 1.0
    materials = [
        {
            "name": k,
            "quantity": round(v, 2),
            "unit": material_units.get(k, ""),
            "share": round((v / total_qty) * 100, 1),
        }
        for k, v in sorted(material_totals.items(), key=lambda x: x[1], reverse=True)[:20]
    ]

    cat_total = sum(category_totals.values()) or 1.0
    categories = [
        {
            "name": k,
            "quantity": round(v, 2),
            "share": round((v / cat_total) * 100, 1),
        }
        for k, v in sorted(category_totals.items(), key=lambda x: x[1], reverse=True)
    ]

    cut = float(material_totals.get("Earthwork Cut", 0))
    fill = float(material_totals.get("Earthwork Fill", 0))
    balance = round(cut - fill, 2)
    if abs(balance) < 0.01:
        balance_label = "balanced"
    elif balance > 0:
        balance_label = "cut surplus"
    else:
        balance_label = "fill surplus"

    by_project = sorted(
        [
            {"project_id": v["project_id"], "name": v["name"], "amount": round(v["amount"], 2)}
            for v in cost_by_project.values()
        ],
        key=lambda x: x["amount"],
        reverse=True,
    )

    return {
        "materials": materials,
        "categories": categories,
        "earthwork": {
            "cut": round(cut, 2),
            "fill": round(fill, 2),
            "balance": balance,
            "balance_label": balance_label,
        },
        "costs": {
            "total_estimated": round(cost_total, 2),
            "by_project": by_project,
        },
        "pavement": {
            "GSB": round(float(material_totals.get("GSB", 0)), 2),
            "WMM": round(float(material_totals.get("WMM", 0)), 2),
            "DBM": round(float(material_totals.get("DBM", 0)), 2),
            "Bituminous Concrete": round(float(material_totals.get("Bituminous Concrete", 0)), 2),
            "Asphalt": round(float(material_totals.get("Asphalt", 0)), 2),
        },
        "meta": {
            "boq_count": len(boqs),
            "estimate_count": len(estimates),
            "project_count": len(project_ids),
            "item_count": item_count,
            "last_updated": last_updated.isoformat() if last_updated else None,
            "has_boqs": len(boqs) > 0,
            "has_estimates": len(estimates) > 0,
        },
    }


def _compare_snapshots(a: dict, b: dict, a_id: int, a_name: str, b_id: int, b_name: str) -> dict:
    a_mat = {m["name"]: m["quantity"] for m in a["materials"]}
    b_mat = {m["name"]: m["quantity"] for m in b["materials"]}
    names = sorted(set(a_mat) | set(b_mat))
    material_deltas = []
    for name in names:
        av = a_mat.get(name, 0.0)
        bv = b_mat.get(name, 0.0)
        if av == 0 and bv == 0:
            continue
        material_deltas.append(
            {
                "name": name,
                "a": av,
                "b": bv,
                "delta": round(bv - av, 2),
            }
        )
    material_deltas.sort(key=lambda x: abs(x["delta"]), reverse=True)

    return {
        "a": {"project_id": a_id, "name": a_name, **a},
        "b": {"project_id": b_id, "name": b_name, **b},
        "delta": {
            "cost": round(b["costs"]["total_estimated"] - a["costs"]["total_estimated"], 2),
            "cut": round(b["earthwork"]["cut"] - a["earthwork"]["cut"], 2),
            "fill": round(b["earthwork"]["fill"] - a["earthwork"]["fill"], 2),
            "materials": material_deltas[:15],
        },
    }


@router.get("/analytics")
def get_analytics(
    project_id: int | None = None,
    status: ProjectStatus | None = None,
    range: str = "all",
    compare_a: int | None = None,
    compare_b: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    accessible = _accessible_project_ids(current_user)
    range_key = range if range in {"7d", "30d", "all"} else "all"
    since = _resolve_since(range_key)

    proj_stmt = select(Project).where(Project.id.in_(accessible))
    if project_id is not None:
        proj_stmt = proj_stmt.where(Project.id == project_id)
    elif status is not None:
        proj_stmt = proj_stmt.where(Project.status == status)

    projects = db.scalars(proj_stmt.order_by(Project.name.asc())).all()
    # Ensure requested project is accessible
    if project_id is not None and not projects:
        projects = []

    scoped_ids = [p.id for p in projects]
    snapshot = _build_analytics_snapshot(db, scoped_ids, since)
    snapshot["filters"] = {
        "project_id": project_id,
        "status": status.value if status else None,
        "range": range_key,
    }
    snapshot["meta"]["range"] = range_key

    compare_payload = None
    if compare_a is not None and compare_b is not None and compare_a != compare_b:
        a_proj = db.scalar(select(Project).where(Project.id == compare_a, Project.id.in_(accessible)))
        b_proj = db.scalar(select(Project).where(Project.id == compare_b, Project.id.in_(accessible)))
        if a_proj and b_proj:
            a_snap = _build_analytics_snapshot(db, [a_proj.id], since)
            b_snap = _build_analytics_snapshot(db, [b_proj.id], since)
            compare_payload = _compare_snapshots(a_snap, b_snap, a_proj.id, a_proj.name, b_proj.id, b_proj.name)

    snapshot["compare"] = compare_payload
    return snapshot
