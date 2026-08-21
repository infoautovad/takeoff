"""Project-scoped engineering chat with action execution."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analysis import ChatMessage, DocumentAnalysis
from app.models.eoq import EOQ, EOQItem
from app.models.document import Document
from app.models.project import Project
from app.services.ai_analysis import answer_engineering_question
from app.services.chat_agent import (
    execute_actions,
    format_action_answer,
    help_text,
    plan_actions,
)
from app.services.processing import load_findings


def build_project_context(db: Session, project: Project) -> str:
    parts: list[str] = [
        f"Project: {project.name}",
        f"Location: {project.location or 'N/A'}",
        f"State/Country: {project.state or 'N/A'}, {project.country}",
        f"Description: {project.description or 'N/A'}",
        "",
        "You are AutoVAD inside the AutoVAD web app. "
        "The user is logged in. Actions like analyze, generate EOQ, and export Excel "
        "are executed by the app agent — do not say you cannot update Excel; "
        "the agent handles downloads.",
    ]

    documents = list(db.scalars(select(Document).where(Document.project_id == project.id)).all())
    parts.append(f"Documents ({len(documents)}):")
    for doc in documents:
        parts.append(f"- [{doc.id}] {doc.original_filename} status={doc.processing_status.value}")

    analyses = db.scalars(select(DocumentAnalysis).where(DocumentAnalysis.project_id == project.id)).all()
    for analysis in analyses:
        findings = load_findings(analysis)
        parts.append(f"\nAnalysis for document {analysis.document_id} ({analysis.engine}):")
        parts.append(analysis.summary or "")
        for fact in findings.get("facts") or []:
            parts.append(f"FACT: {fact}")
        for item in findings.get("items") or []:
            parts.append(
                "ITEM: "
                f"{item.get('description')} = {item.get('quantity')} {item.get('unit')} "
                f"(confidence={item.get('confidence')}, source={item.get('source_reference')})"
            )
        if analysis.extracted_text:
            parts.append("EXTRACTED_TEXT_EXCERPT:")
            parts.append(analysis.extracted_text[:8000])

    eoqs = db.scalars(select(EOQ).where(EOQ.project_id == project.id).order_by(EOQ.version.desc())).all()
    for eoq in eoqs[:2]:
        parts.append(f"\nEOQ v{eoq.version}: {eoq.title} ({eoq.status.value})")
        items = db.scalars(select(EOQItem).where(EOQItem.eoq_id == eoq.id)).all()
        for item in items:
            parts.append(
                f"EOQ_ITEM {item.item_number}: CSI={item.csi_code or item.item_code or '—'} | "
                f"{item.description} | {float(item.quantity):.2f} {item.unit} | "
                f"source={item.source_reference} | confidence={item.confidence}"
            )

    return "\n".join(parts)


def ask_project(
    db: Session,
    *,
    project: Project,
    user_id: int,
    question: str,
) -> ChatMessage:
    q = question.strip()
    documents = list(db.scalars(select(Document).where(Document.project_id == project.id)).all())
    actions = plan_actions(q, documents)

    sources: list[dict] = []
    answer = ""

    if actions:
        # Special-case help text
        if len(actions) == 1 and actions[0].name == "help":
            answer = help_text()
            sources = [{"type": "action", "action": "help", "ok": True}]
        else:
            results = execute_actions(db, project=project, user_id=user_id, actions=actions)
            answer, sources = format_action_answer(results, question=q)
            # For help mixed in
            if any(a.name == "help" for a in actions) and not answer:
                answer = help_text()
    else:
        context = build_project_context(db, project)
        result = answer_engineering_question(question=q, context=context)
        answer = result.get("answer") or ""
        sources = result.get("sources") or []

    user_msg = ChatMessage(
        project_id=project.id,
        user_id=user_id,
        role="user",
        content=q,
    )
    assistant_msg = ChatMessage(
        project_id=project.id,
        user_id=user_id,
        role="assistant",
        content=answer,
        sources_json=json.dumps(sources, ensure_ascii=True),
    )
    db.add(user_msg)
    db.add(assistant_msg)
    db.commit()
    db.refresh(assistant_msg)
    return assistant_msg


def list_chat(db: Session, project_id: int, limit: int = 50) -> list[ChatMessage]:
    return list(
        db.scalars(
            select(ChatMessage)
            .where(ChatMessage.project_id == project_id)
            .order_by(ChatMessage.created_at.asc())
            .limit(limit)
        ).all()
    )
