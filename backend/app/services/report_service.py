from __future__ import annotations

import json
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.boq import BOQ
from app.models.cost import CostEstimate
from app.models.document import Document
from app.models.project import Project
from app.models.report import Report


def generate_project_reports(db: Session, project: Project, user_id: int) -> list[Report]:
    documents = list(db.scalars(select(Document).where(Document.project_id == project.id)).all())
    boqs = list(
        db.scalars(
            select(BOQ).options(selectinload(BOQ.items)).where(BOQ.project_id == project.id).order_by(BOQ.version.desc())
        ).all()
    )
    latest_boq = boqs[0] if boqs else None
    estimates = list(
        db.scalars(select(CostEstimate).where(CostEstimate.project_id == project.id).order_by(CostEstimate.created_at.desc())).all()
    )
    latest_cost = estimates[0] if estimates else None

    category_qty: dict[str, float] = defaultdict(float)
    if latest_boq:
        for item in latest_boq.items:
            category_qty[item.category or "General"] += float(item.quantity)

    reports_spec = [
        (
            "executive_summary",
            "Executive Summary",
            f"Project '{project.name}' has {len(documents)} documents, {len(boqs)} Estimate Of Quantities version(s)"
            + (f", latest estimated cost {latest_cost.total_amount} {latest_cost.currency}." if latest_cost else "."),
            {
                "project": project.name,
                "location": project.location,
                "status": project.status.value,
                "documents": len(documents),
                "boq_versions": len(boqs),
                "latest_cost": float(latest_cost.total_amount) if latest_cost else None,
            },
        ),
        (
            "boq_report",
            "Estimate Of Quantities Report",
            f"Latest Estimate Of Quantities contains {len(latest_boq.items) if latest_boq else 0} items.",
            {
                "boq": latest_boq.title if latest_boq else None,
                "items": [
                    {
                        "item_number": i.item_number,
                        "description": i.description,
                        "quantity": float(i.quantity),
                        "unit": i.unit,
                        "confidence": float(i.confidence) if i.confidence is not None else None,
                        "source": i.source_reference,
                        "status": i.status.value,
                    }
                    for i in (latest_boq.items if latest_boq else [])
                ],
            },
        ),
        (
            "material_report",
            "Material / Quantity Report",
            "Quantities grouped by category.",
            {"category_totals": dict(category_qty)},
        ),
        (
            "pavement_report",
            "Pavement Report",
            "Pavement-related Estimate Of Quantities items.",
            {
                "items": [
                    {
                        "description": i.description,
                        "quantity": float(i.quantity),
                        "unit": i.unit,
                    }
                    for i in (latest_boq.items if latest_boq else [])
                    if (i.category or "").lower() == "pavement"
                    or any(k in i.description.lower() for k in ("gsb", "wmm", "dbm", "asphalt", "bituminous"))
                ]
            },
        ),
        (
            "earthwork_report",
            "Earthwork Report",
            "Cut/fill and earthwork items.",
            {
                "items": [
                    {
                        "description": i.description,
                        "quantity": float(i.quantity),
                        "unit": i.unit,
                    }
                    for i in (latest_boq.items if latest_boq else [])
                    if "earth" in (i.category or "").lower()
                    or any(k in i.description.lower() for k in ("cut", "fill", "excavation", "embankment"))
                ]
            },
        ),
        (
            "cost_estimation_report",
            "Cost Estimation Report",
            f"Total estimated cost: {latest_cost.total_amount if latest_cost else 'N/A'}.",
            json.loads(latest_cost.breakdown_json) if latest_cost and latest_cost.breakdown_json else {},
        ),
        (
            "drawing_analysis_report",
            "Drawing Analysis Report",
            f"{len(documents)} uploaded document(s) with processing statuses.",
            {
                "documents": [
                    {
                        "id": d.id,
                        "filename": d.original_filename,
                        "status": d.processing_status.value,
                        "type": d.document_type.value,
                        "pages": d.page_count,
                    }
                    for d in documents
                ]
            },
        ),
    ]

    created: list[Report] = []
    for report_type, title, summary, content in reports_spec:
        report = Report(
            project_id=project.id,
            report_type=report_type,
            title=title,
            summary=summary,
            content_json=json.dumps(content, ensure_ascii=True),
            created_by=user_id,
        )
        db.add(report)
        created.append(report)
    db.commit()
    for r in created:
        db.refresh(r)
    return created
