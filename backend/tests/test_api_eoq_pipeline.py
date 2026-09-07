"""API-level EOQ generation regression tests."""

from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.api.deps import get_current_user, get_db
from app.api.routes import eoq as eoq_routes
from app.database import Base
from app.models.analysis import DocumentAnalysis
from app.models.document import Document, DocumentType, ProcessingStatus
from app.models.project import Project, ProjectMember, ProjectMemberRole, ProjectStatus
from app.models.user import SubscriptionPlan, User, UserRole


def _build_context(items_by_document: list[list[dict[str, Any]]]) -> tuple[TestClient, int, list[int]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    user = User(
        email="qa-user@autovad.test",
        full_name="QA User",
        hashed_password="not-used-in-api-test",
        role=UserRole.DESIGN_ENGINEER,
        plan=SubscriptionPlan.BUSINESS,
        is_active=True,
        is_blocked=False,
    )
    db.add(user)
    db.flush()

    project = Project(
        name="EOQ API Test Project",
        description="Regression",
        location="Austin, TX",
        client_name="Test DOT",
        country="USA",
        state="TX",
        status=ProjectStatus.ACTIVE,
        owner_id=user.id,
    )
    db.add(project)
    db.flush()
    db.add(
        ProjectMember(
            project_id=project.id,
            user_id=user.id,
            role=ProjectMemberRole.OWNER,
        )
    )

    doc_ids: list[int] = []
    for idx, items in enumerate(items_by_document, start=1):
        doc = Document(
            project_id=project.id,
            uploaded_by=user.id,
            original_filename=f"test_{idx}.pdf",
            stored_filename=f"stored_{idx}.pdf",
            storage_key=f"projects/{project.id}/test_{idx}.pdf",
            content_type="application/pdf",
            file_size=4096,
            document_type=DocumentType.PDF,
            processing_status=ProcessingStatus.COMPLETED,
            page_count=12,
            revision_label="R1",
            notes=None,
            error_message=None,
        )
        db.add(doc)
        db.flush()
        doc_ids.append(doc.id)
        db.add(
            DocumentAnalysis(
                document_id=doc.id,
                project_id=project.id,
                engine="heuristic",
                summary="test analysis",
                extracted_text="",
                findings_json=json.dumps(
                    {
                        "facts": [],
                        "items": items,
                        "needs_review": False,
                    }
                ),
            )
        )

    db.commit()
    project_id = project.id
    user_id = user.id
    db.close()

    app = FastAPI()
    app.include_router(eoq_routes.router, prefix="/api/eoq")

    def override_get_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    def override_current_user():
        session = SessionLocal()
        try:
            current = session.get(User, user_id)
            assert current is not None
            return current
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_current_user
    return TestClient(app), project_id, doc_ids


def test_generate_eoq_api_applies_schedule_priority_validation():
    client, project_id, _doc_ids = _build_context(
        [
            [
                {
                    "description": "Traffic Control",
                    "unit": "SqFt",
                    "quantity": 624,
                    "item_code": "634.0110",
                    "calculation_method": "Extracted from Estimate Of Quantities schedule",
                    "source_reference": "Bid table p.3",
                    "confidence": 98,
                },
                {
                    "description": "Traffic Control",
                    "unit": "SqFt",
                    "quantity": 710,
                    "calculation_method": "Graphic count from signs",
                    "source_reference": "Sheet F9",
                    "confidence": 80,
                },
            ]
        ]
    )
    try:
        res = client.post(f"/api/eoq/projects/{project_id}/generate", json={})
        assert res.status_code == 200, res.text
        body = res.json()
        traffic_rows = [row for row in body["items"] if str(row.get("description", "")).lower() == "traffic control"]
        assert len(traffic_rows) == 1
        assert abs(float(traffic_rows[0]["quantity"]) - 624.0) < 0.01
        assert "deterministic validation" in str(body.get("notes") or "").lower()
    finally:
        client.close()


def test_generate_eoq_api_document_scope_only_uses_selected_documents():
    client, project_id, doc_ids = _build_context(
        [
            [
                {
                    "description": "8-Inch Water Main",
                    "unit": "LF",
                    "quantity": 120,
                    "source_reference": "Sheet U2",
                    "confidence": 92,
                }
            ],
            [
                {
                    "description": "Sanitary Sewer Manhole",
                    "unit": "EA",
                    "quantity": 4,
                    "source_reference": "Sheet S4",
                    "confidence": 93,
                }
            ],
        ]
    )
    try:
        res = client.post(
            f"/api/eoq/projects/{project_id}/generate",
            json={"document_ids": [doc_ids[0]]},
        )
        assert res.status_code == 200, res.text
        body = res.json()
        descriptions = {str(row.get("description") or "") for row in body["items"]}
        assert any("Water Main" in desc for desc in descriptions)
        assert not any("Sanitary Sewer Manhole" in desc for desc in descriptions)
    finally:
        client.close()


def test_generate_eoq_api_maps_to_autovad_master_template(monkeypatch):
    from app.services.bid_service import MasterBidTemplateLine

    def fake_master_template_lines(*, force_reload: bool = False):
        _ = force_reload
        return (
            "AutoVAD master template (Bid Item List 2026.xlsx)",
            [
                MasterBidTemplateLine(
                    id=1,
                    line_number="4",
                    csi_code=None,
                    item_code="634.0120",
                    description="Traffic Control, Miscellaneous",
                    unit="ls",
                    default_rate=None,
                    sort_order=1,
                ),
                MasterBidTemplateLine(
                    id=2,
                    line_number="1",
                    csi_code=None,
                    item_code="9.0010",
                    description="Mobilization",
                    unit="ls",
                    default_rate=None,
                    sort_order=2,
                ),
            ],
            None,
        )

    monkeypatch.setattr(
        "app.services.eoq_service.get_autovad_master_template_lines",
        fake_master_template_lines,
    )

    client, project_id, _doc_ids = _build_context(
        [
            [
                {
                    "description": "Temporary traffic control miscellaneous work",
                    "unit": "LS",
                    "quantity": 1,
                    "source_reference": "Sheet F2",
                    "confidence": 92,
                }
            ]
        ]
    )
    try:
        res = client.post(f"/api/eoq/projects/{project_id}/generate", json={})
        assert res.status_code == 200, res.text
        body = res.json()
        row = next(
            r
            for r in body["items"]
            if str(r.get("description") or "").lower() == "traffic control, miscellaneous"
        )
        assert row["item_code"] == "634.0120"
        assert str(row["unit"]).upper() == "LS"
        assert row["bid_template_line_id"] == 1
        assert "autovad master template" in str(body.get("notes") or "").lower()
    finally:
        client.close()
