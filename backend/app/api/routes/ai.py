import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routes.projects import _get_accessible_project
from app.database import get_db
from app.models.analysis import DocumentAnalysis
from app.models.document import Document
from app.models.user import User
from app.schemas.ai import AnalysisOut, ChatAskIn, ChatMessageOut, ProcessResultOut
from app.services.activity import log_activity
from app.services.chat_service import ask_project, list_chat
from app.services.notifications import notify
from app.services.processing import load_findings, process_document, process_project_documents
from app.services.openai_client import openai_status
from app.services.cad.aps_client import aps_status
from app.config import get_settings

router = APIRouter()


@router.get("/status")
def intelligence_status() -> dict:
    """OpenAI + Autodesk APS readiness for document AI, chat, and CAD enrichment."""
    settings = get_settings()
    oai = openai_status()
    aps = aps_status()
    from app.services.cad.design_automation import design_automation_status

    da = design_automation_status()
    dwg_mode = "needs_autodesk"
    if aps["configured"] and da["configured"]:
        dwg_mode = "design_automation"
    elif aps["configured"]:
        dwg_mode = "autodesk_model_derivative"
    return {
        "openai": oai,
        "autodesk_aps": aps,
        "design_automation": da,
        "cad_engine_enabled": settings.cad_engine_enabled,
        "cad_openai_enrichment": settings.cad_openai_enrichment,
        "modes": {
            "document_analysis": oai["mode"],
            "engineering_chat": oai["mode"],
            "cad_dxf_landxml": "local",
            "cad_dwg": dwg_mode,
            "cad_quantity_enrichment": (
                "openai" if oai["configured"] and settings.cad_openai_enrichment else "rules_only"
            ),
        },
        "setup_hints": {
            "openai": "Set OPENAI_API_KEY (and optional OPENAI_MODEL) in backend/.env, then restart backend.",
            "autodesk_aps": (
                "Create an APS app at https://aps.autodesk.com, enable Design Automation + Model Derivative, "
                "set AUTODESK_CLIENT_ID/SECRET in backend/.env, then POST /api/cad/design-automation/setup."
            ),
            "design_automation": da.get("setup_hint"),
        },
    }


def _analysis_out(analysis: DocumentAnalysis) -> AnalysisOut:
    return AnalysisOut(
        id=analysis.id,
        document_id=analysis.document_id,
        project_id=analysis.project_id,
        engine=analysis.engine,
        summary=analysis.summary,
        findings=load_findings(analysis),
        created_at=analysis.created_at,
        updated_at=analysis.updated_at,
    )


@router.post("/documents/{document_id}/analyze", response_model=ProcessResultOut)
def analyze_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProcessResultOut:
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    _get_accessible_project(db, document.project_id, current_user)

    try:
        analysis = process_document(db, document)
        db.refresh(document)
        log_activity(
            db,
            user_id=current_user.id,
            project_id=document.project_id,
            action="document_analyzed",
            message=f"AI analyzed '{document.original_filename}'",
            entity_type="document",
            entity_id=document.id,
        )
        failed = document.processing_status.value == "failed"
        if not failed:
            notify(
                db,
                user_id=current_user.id,
                project_id=document.project_id,
                title="Processing completed",
                message=f"Analysis finished for '{document.original_filename}'",
                category="analysis",
            )
        return ProcessResultOut(
            document_id=document.id,
            status=document.processing_status.value,
            analysis=_analysis_out(analysis),
            error=document.error_message if failed else None,
        )
    except Exception as exc:
        return ProcessResultOut(
            document_id=document.id,
            status="failed",
            error=str(exc),
        )


@router.post("/projects/{project_id}/analyze", response_model=list[ProcessResultOut])
def analyze_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ProcessResultOut]:
    _get_accessible_project(db, project_id, current_user)
    documents = list(db.scalars(select(Document).where(Document.project_id == project_id)).all())
    if not documents:
        raise HTTPException(status_code=400, detail="No documents to analyze")

    results: list[ProcessResultOut] = []
    try:
        analyses = process_project_documents(db, project_id)
        by_doc = {a.document_id: a for a in analyses}
        for doc in documents:
            db.refresh(doc)
            analysis = by_doc.get(doc.id)
            results.append(
                ProcessResultOut(
                    document_id=doc.id,
                    status=doc.processing_status.value,
                    analysis=_analysis_out(analysis) if analysis else None,
                    error=doc.error_message,
                )
            )
        log_activity(
            db,
            user_id=current_user.id,
            project_id=project_id,
            action="project_analyzed",
            message=f"AI analyzed {len(documents)} document(s)",
            entity_type="project",
            entity_id=project_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {exc}") from exc
    return results


@router.get("/projects/{project_id}/analyses", response_model=list[AnalysisOut])
def get_project_analyses(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AnalysisOut]:
    _get_accessible_project(db, project_id, current_user)
    analyses = db.scalars(select(DocumentAnalysis).where(DocumentAnalysis.project_id == project_id)).all()
    return [_analysis_out(a) for a in analyses]


@router.get("/projects/{project_id}/chat", response_model=list[ChatMessageOut])
def get_chat_history(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ChatMessageOut]:
    _get_accessible_project(db, project_id, current_user)
    messages = list_chat(db, project_id)
    out: list[ChatMessageOut] = []
    for m in messages:
        sources = []
        if m.sources_json:
            try:
                sources = json.loads(m.sources_json)
            except json.JSONDecodeError:
                sources = []
        out.append(
            ChatMessageOut(
                id=m.id,
                project_id=m.project_id,
                user_id=m.user_id,
                role=m.role,
                content=m.content,
                sources=sources,
                created_at=m.created_at,
            )
        )
    return out


@router.post("/projects/{project_id}/chat", response_model=ChatMessageOut, status_code=status.HTTP_201_CREATED)
def ask_chat(
    project_id: int,
    payload: ChatAskIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatMessageOut:
    project = _get_accessible_project(db, project_id, current_user)
    message = ask_project(db, project=project, user_id=current_user.id, question=payload.question.strip())
    sources = []
    if message.sources_json:
        try:
            sources = json.loads(message.sources_json)
        except json.JSONDecodeError:
            sources = []
    return ChatMessageOut(
        id=message.id,
        project_id=message.project_id,
        user_id=message.user_id,
        role=message.role,
        content=message.content,
        sources=sources,
        created_at=message.created_at,
    )
