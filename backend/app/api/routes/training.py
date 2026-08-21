"""Admin Training Lab API — gold cases, AutoVAD runs, training reports."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.database import get_db
from app.models.user import User
from app.services import training_service as svc

router = APIRouter()


class CaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    notes: str | None = None


class CaseUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    notes: str | None = None
    status: str | None = None


class ExpectedPayload(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)
    id: str | None = None
    name: str | None = None
    notes: str | None = None


@router.get("/overview")
def training_overview(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> dict[str, Any]:
    cases = svc.list_cases(db)
    ready = sum(1 for c in cases if c.status.value == "ready" or str(c.status) == "ready")
    runs = 0
    completed = 0
    for c in cases:
        detail = svc.get_case(db, c.id)
        if not detail:
            continue
        for r in detail.runs or []:
            runs += 1
            if str(getattr(r.status, "value", r.status)) == "completed":
                completed += 1
    return {
        "cases": len(cases),
        "ready_cases": ready,
        "runs": runs,
        "completed_runs": completed,
        "purpose": "Upload sample plans + original items, run AutoVAD, get training diff reports for agent fine-tuning.",
    }


@router.get("/cases")
def list_cases(db: Session = Depends(get_db), _: User = Depends(get_current_admin)) -> list[dict]:
    return [svc.case_to_dict(c) for c in svc.list_cases(db)]


@router.post("/cases", status_code=status.HTTP_201_CREATED)
def create_case(
    payload: CaseCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> dict:
    case = svc.create_case(
        db,
        user_id=admin.id,
        name=payload.name,
        description=payload.description,
        notes=payload.notes,
    )
    return svc.case_to_dict(case)


@router.get("/cases/{case_id}")
def get_case(case_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_admin)) -> dict:
    case = svc.get_case(db, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Training case not found")
    return svc.case_to_dict(case, include_runs=True)


@router.patch("/cases/{case_id}")
def patch_case(
    case_id: int,
    payload: CaseUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> dict:
    case = svc.get_case(db, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Training case not found")
    try:
        case = svc.update_case(
            db,
            case,
            name=payload.name,
            description=payload.description,
            notes=payload.notes,
            status=payload.status,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return svc.case_to_dict(case, include_runs=True)


@router.delete("/cases/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_case(case_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_admin)) -> None:
    case = svc.get_case(db, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Training case not found")
    svc.delete_case(db, case)


@router.post("/cases/{case_id}/sample")
async def upload_sample(
    case_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> dict:
    case = svc.get_case(db, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Training case not found")
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename required")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    case = await svc.save_sample_file(db, case, filename=file.filename, data=data)
    return svc.case_to_dict(case, include_runs=True)


@router.post("/cases/{case_id}/expected")
async def upload_expected(
    case_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> dict:
    """Upload original Estimate Of Quantities: PDF, Excel, CSV, image (or JSON)."""
    case = svc.get_case(db, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Training case not found")
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename required")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    try:
        case = await svc.save_expected_file(db, case, filename=file.filename, data=data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse original EOQ file: {exc}") from exc
    return svc.case_to_dict(case, include_runs=True)


@router.put("/cases/{case_id}/expected")
def put_expected(
    case_id: int,
    payload: ExpectedPayload,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> dict:
    case = svc.get_case(db, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Training case not found")
    try:
        case = svc.set_expected_json(db, case, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return svc.case_to_dict(case, include_runs=True)


@router.put("/cases/{case_id}/bid-catalog")
def put_bid_catalog(
    case_id: int,
    payload: list[dict[str, Any]] | dict[str, Any],
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> dict:
    case = svc.get_case(db, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Training case not found")
    case = svc.set_bid_catalog_json(db, case, payload)
    return svc.case_to_dict(case, include_runs=True)


@router.post("/cases/{case_id}/analyze")
def analyze_case(
    case_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> dict:
    """Stage 1: Analyze sample plan → AutoVAD Estimate Of Quantities."""
    case = svc.get_case(db, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Training case not found")
    try:
        case = svc.run_autovad_analyze(db, case)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return svc.case_to_dict(case, include_runs=True)


@router.post("/cases/{case_id}/evaluate")
def evaluate_case(
    case_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> dict:
    """Stage 3: Compare AutoVAD EOQ vs original EOQ → training report."""
    case = svc.get_case(db, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Training case not found")
    try:
        run = svc.run_evaluation(db, case, user_id=admin.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        runs = svc.list_runs(db, case_id)
        if runs and str(getattr(runs[0].status, "value", runs[0].status)) == "failed":
            return svc.run_to_dict(runs[0])
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return svc.run_to_dict(run)


@router.post("/cases/{case_id}/run")
def run_case(
    case_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> dict:
    """Legacy alias: evaluate (analyze first if needed). Prefer /analyze then /evaluate."""
    case = svc.get_case(db, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Training case not found")
    try:
        run = svc.run_training_case(db, case, user_id=admin.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        runs = svc.list_runs(db, case_id)
        if runs and str(getattr(runs[0].status, "value", runs[0].status)) == "failed":
            return svc.run_to_dict(runs[0])
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return svc.run_to_dict(run)


@router.get("/cases/{case_id}/runs")
def case_runs(case_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_admin)) -> list[dict]:
    case = svc.get_case(db, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Training case not found")
    return [svc.run_to_dict(r) for r in svc.list_runs(db, case_id)]


@router.get("/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_admin)) -> dict:
    run = svc.get_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Training run not found")
    return svc.run_to_dict(run)
