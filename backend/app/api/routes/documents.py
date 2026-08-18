from pathlib import Path

import fitz
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routes.projects import _get_accessible_project
from app.config import get_settings
from app.database import get_db
from app.models.analysis import DocumentAnalysis
from app.models.document import Document, DocumentType, ProcessingStatus
from app.models.user import User
from app.schemas.document import DocumentOut
from app.services.activity import log_activity
from app.services.documents import detect_document_type, guess_content_type
from app.services.notifications import notify
from app.services.storage import storage_service

router = APIRouter()
settings = get_settings()


@router.get("/project/{project_id}", response_model=list[DocumentOut])
def list_project_documents(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Document]:
    _get_accessible_project(db, project_id, current_user)
    return list(
        db.scalars(
            select(Document)
            .where(Document.project_id == project_id)
            .order_by(Document.created_at.desc())
        ).all()
    )


@router.post("/project/{project_id}/upload", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    project_id: int,
    file: UploadFile = File(...),
    revision_label: str | None = Form(default=None),
    notes: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Document:
    _get_accessible_project(db, project_id, current_user)

    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    ext = Path(file.filename).suffix.lower().lstrip(".")
    if ext not in settings.allowed_extension_list:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '.{ext}'. Allowed: {', '.join(sorted(settings.allowed_extension_list))}",
        )

    data = await file.read()
    # max_upload_size_mb <= 0 means unlimited (no size rejection).
    if settings.max_upload_size_mb > 0:
        max_bytes = settings.max_upload_size_mb * 1024 * 1024
        if len(data) > max_bytes:
            raise HTTPException(
                status_code=400,
                detail=f"File exceeds {settings.max_upload_size_mb} MB limit",
            )

    key = storage_service.build_key(project_id, file.filename)
    await storage_service.save_file(key, data)

    document = Document(
        project_id=project_id,
        uploaded_by=current_user.id,
        original_filename=file.filename,
        stored_filename=Path(key).name,
        storage_key=key,
        content_type=file.content_type or guess_content_type(file.filename),
        file_size=len(data),
        document_type=detect_document_type(file.filename),
        processing_status=ProcessingStatus.UPLOADED,
        revision_label=revision_label,
        notes=notes,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    log_activity(
        db,
        user_id=current_user.id,
        project_id=project_id,
        action="document_uploaded",
        message=f"Uploaded '{document.original_filename}'",
        entity_type="document",
        entity_id=document.id,
    )
    notify(
        db,
        user_id=current_user.id,
        project_id=project_id,
        title="File uploaded",
        message=f"Uploaded '{document.original_filename}'",
        category="upload",
    )
    return document


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Document:
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    _get_accessible_project(db, document.project_id, current_user)
    return document


@router.get("/{document_id}/download")
def download_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    _get_accessible_project(db, document.project_id, current_user)

    path = storage_service.resolve_local_path(document.storage_key)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File missing from storage")

    return FileResponse(
        path,
        media_type=document.content_type,
        filename=document.original_filename,
    )


@router.get("/{document_id}/viewer")
def document_viewer_meta(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    _get_accessible_project(db, document.project_id, current_user)

    analysis = db.scalar(select(DocumentAnalysis).where(DocumentAnalysis.document_id == document_id))
    page_count = document.page_count or 1
    text_pages: list[dict] = []
    if analysis and analysis.extracted_text:
        chunks = analysis.extracted_text.split("--- Page ")
        for chunk in chunks:
            chunk = chunk.strip()
            if not chunk:
                continue
            if "---" in chunk[:12] or chunk[0:1].isdigit():
                try:
                    num_str, body = chunk.split("---", 1)
                    page_no = int(num_str.strip())
                    text_pages.append({"page": page_no, "text": body.strip()[:8000]})
                except Exception:
                    text_pages.append({"page": len(text_pages) + 1, "text": chunk[:8000]})
            else:
                text_pages.append({"page": 1, "text": chunk[:8000]})
    if not text_pages and analysis and analysis.extracted_text:
        text_pages = [{"page": 1, "text": analysis.extracted_text[:8000]}]

    return {
        "id": document.id,
        "filename": document.original_filename,
        "document_type": document.document_type.value,
        "page_count": page_count,
        "processing_status": document.processing_status.value,
        "has_pdf_preview": document.document_type == DocumentType.PDF,
        "text_pages": text_pages,
        "summary": analysis.summary if analysis else None,
    }


@router.get("/{document_id}/pages/{page_number}/image")
def document_page_image(
    document_id: int,
    page_number: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    _get_accessible_project(db, document.project_id, current_user)
    if document.document_type != DocumentType.PDF:
        raise HTTPException(status_code=400, detail="Page preview is available for PDF files")

    path = storage_service.resolve_local_path(document.storage_key)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File missing from storage")

    with fitz.open(path) as doc:
        if page_number < 1 or page_number > doc.page_count:
            raise HTTPException(status_code=404, detail="Page not found")
        page = doc.load_page(page_number - 1)
        pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
        png_bytes = pix.tobytes("png")
        document.page_count = doc.page_count
        db.commit()

    return Response(content=png_bytes, media_type="image/png")


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    project = _get_accessible_project(db, document.project_id, current_user)
    if project.owner_id != current_user.id and document.uploaded_by != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed to delete this document")

    filename = document.original_filename
    project_id = document.project_id
    storage_service.delete_file(document.storage_key)
    db.delete(document)
    db.commit()

    log_activity(
        db,
        user_id=current_user.id,
        project_id=project_id,
        action="document_deleted",
        message=f"Deleted '{filename}'",
        entity_type="document",
        entity_id=document_id,
    )
