"""Shared OpenAI client for document AI, chat, and CAD enrichment.

Uses OPENAI_MODEL from settings (default: gpt-5.6-terra).
Prefer Responses API when available; fall back to Chat Completions.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.config import get_settings


def openai_configured() -> bool:
    key = (get_settings().openai_api_key or "").strip()
    return bool(key)


def openai_status() -> dict[str, Any]:
    settings = get_settings()
    configured = openai_configured()
    return {
        "configured": configured,
        "model": settings.openai_model,
        "mode": "openai" if configured else "heuristic",
    }


def get_openai_client():
    if not openai_configured():
        raise RuntimeError("OPENAI_API_KEY is not configured")
    from openai import OpenAI

    # Long timeout per call: large vision batches / takeoff prompts can run many minutes.
    # Retries stay low so a stuck call does not multiply wait time endlessly.
    return OpenAI(
        api_key=get_settings().openai_api_key.strip(),
        timeout=3600.0,  # 60 minutes per OpenAI request
        max_retries=2,
    )


def _model_name() -> str:
    return (get_settings().openai_model or "gpt-5.6-terra").strip()


def _supports_custom_temperature(model: str) -> bool:
    """Some GPT-5 family models only allow the default temperature."""
    low = model.lower()
    if "gpt-5" in low or "terra" in low or "o1" in low or "o3" in low or "o4" in low:
        return False
    return True


def ask_openai_json(system: str, user: str, *, temperature: float = 0.1) -> dict[str, Any]:
    """Ask OpenAI and parse a JSON object from the response."""
    raw = ask_openai_text(system=system, user=user, temperature=temperature)
    return _parse_json_object(raw)


def ask_openai_text(system: str, user: str, *, temperature: float = 0.1) -> str:
    return _ask_openai(
        system=system,
        user_text=user,
        images=None,
        temperature=temperature,
    )


def ask_openai_vision_json(
    system: str,
    user: str,
    images: list[dict[str, Any]],
    *,
    temperature: float = 0.1,
) -> dict[str, Any]:
    """Multimodal JSON ask — images are {page, png_b64} dicts."""
    raw = _ask_openai(
        system=system,
        user_text=user,
        images=images,
        temperature=temperature,
    )
    return _parse_json_object(raw)


def _ask_openai(
    *,
    system: str,
    user_text: str,
    images: list[dict[str, Any]] | None,
    temperature: float = 0.1,
) -> str:
    client = get_openai_client()
    model = _model_name()
    use_temp = _supports_custom_temperature(model)
    errors: list[str] = []
    image_parts = images or []

    # 1) Responses API (preferred) — supports input_image
    if hasattr(client, "responses"):
        try:
            user_content: list[dict[str, Any]] = [{"type": "input_text", "text": user_text}]
            for img in image_parts:
                b64 = img.get("png_b64") or img.get("b64")
                if not b64:
                    continue
                page = img.get("page")
                if page:
                    user_content.append({"type": "input_text", "text": f"[Plan sheet page {page}]"})
                user_content.append(
                    {
                        "type": "input_image",
                        "image_url": f"data:image/png;base64,{b64}",
                    }
                )
            kwargs: dict[str, Any] = {
                "model": model,
                "input": [
                    {"role": "system", "content": [{"type": "input_text", "text": system}]},
                    {"role": "user", "content": user_content},
                ],
            }
            if use_temp:
                kwargs["temperature"] = temperature
            response = client.responses.create(**kwargs)
            text = getattr(response, "output_text", None) or _responses_text(response)
            if text and text.strip():
                return text
            errors.append("Responses API returned empty output_text")
        except Exception as exc:
            errors.append(f"Responses API: {exc}")

        if not image_parts:
            try:
                response = client.responses.create(
                    model=model,
                    input=f"{system}\n\n{user_text}",
                )
                text = getattr(response, "output_text", None) or _responses_text(response)
                if text and text.strip():
                    return text
                errors.append("Simple Responses API returned empty output_text")
            except Exception as exc:
                errors.append(f"Simple Responses API: {exc}")

    # 2) Chat Completions fallback (vision via image_url)
    try:
        user_content_chat: list[dict[str, Any]] | str
        if image_parts:
            user_content_chat = [{"type": "text", "text": user_text}]
            for img in image_parts:
                b64 = img.get("png_b64") or img.get("b64")
                if not b64:
                    continue
                page = img.get("page")
                if page:
                    user_content_chat.append({"type": "text", "text": f"[Plan sheet page {page}]"})
                user_content_chat.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    }
                )
        else:
            user_content_chat = user_text

        kwargs = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_content_chat},
            ],
        }
        if use_temp:
            kwargs["temperature"] = temperature
        if "json" in system.lower() or "JSON" in user_text:
            kwargs["response_format"] = {"type": "json_object"}
        completion = client.chat.completions.create(**kwargs)
        content = completion.choices[0].message.content or ""
        if content.strip():
            return content
        errors.append("Chat Completions returned empty content")
    except Exception as exc:
        errors.append(f"Chat Completions: {exc}")

    raise RuntimeError(
        f"OpenAI call failed for model '{model}'. "
        + " | ".join(errors[:3])
        + " Check OPENAI_MODEL against models available on your OpenAI account "
        + "(vision requires a multimodal model)."
    )


def apply_cad_label_enrichment(
    original: list[dict[str, Any]],
    refined: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Overlay AI labels only. Never add, drop, split, or change quantity/unit."""
    if not original:
        return []
    refined = list(refined or [])
    out: list[dict[str, Any]] = []
    for idx, src in enumerate(original):
        row = dict(src)
        if idx < len(refined) and isinstance(refined[idx], dict):
            cand = refined[idx]
            desc = str(cand.get("description") or "").strip()
            if desc:
                row["description"] = desc
            cat = str(cand.get("category") or "").strip()
            if cat:
                row["category"] = cat
            code = cand.get("item_code") or cand.get("csi_code")
            if code:
                row["item_code"] = str(code).strip()
            try:
                conf = float(cand.get("confidence") or 0)
                row["confidence"] = max(float(row.get("confidence") or 0), min(conf, 95.0))
            except (TypeError, ValueError):
                pass
        out.append(row)
    from app.services.traffic_control import consolidate_traffic_control_signs

    out, _ = consolidate_traffic_control_signs(out, allow_online_refresh=False)
    return out


def enrich_cad_quantities_with_openai(
    *,
    filename: str,
    extraction_summary: str,
    stats: dict[str, Any],
    quantities: list[dict[str, Any]],
    layers: list[Any],
    blocks: list[Any],
    pipes: list[Any] | None = None,
    texts: list[Any] | None = None,
) -> list[dict[str, Any]]:
    """Ask OpenAI to rename/classify CAD quantity candidates. Item set and quantities stay fixed."""
    if not openai_configured() or not quantities:
        return quantities

    payload = {
        "filename": filename,
        "summary": extraction_summary,
        "stats": stats,
        "layers": layers[:100],
        "blocks": blocks[:150],
        "pipes": (pipes or [])[:120],
        "texts": (texts or [])[:80],
        "quantities": quantities[:200],
    }
    n = min(len(quantities), 200)
    system = (
        "You are a USA civil estimator labeling CAD takeoff lines. "
        "You may ONLY improve description, category, and item_code. "
        "Return exactly one output item per input item, same order. JSON only."
    )
    user = f"""
Relabel these CAD quantities for a civil EOQ (roads, utilities, dams, reservoirs, buildings).

Hard rules:
- Return EXACTLY {n} items in the SAME order as INPUT quantities.
- Do NOT add, drop, merge, or split lines.
- Do NOT change quantity or unit.
- KEEP pipe SIZE in descriptions (e.g. "8-Inch Water Main").
- Prefer network-specific names: Water / Sanitary / Storm.
- TRAFFIC SIGNS: description "Traffic Control" is already rolled up — do not split it.
- Preserve calculation_method and source_reference.

INPUT_JSON:
{json.dumps(payload, ensure_ascii=True)[:50000]}

Return JSON:
{{
  "items": [
    {{
      "description": "8-Inch Water Main",
      "category": "Watermain",
      "item_code": null,
      "confidence": 92
    }}
  ]
}}
"""
    try:
        data = ask_openai_json(system, user)
        items = data.get("items") or []
        return apply_cad_label_enrichment(quantities, items)
    except Exception:
        return quantities


def _responses_text(response: Any) -> str:
    chunks: list[str] = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            text = getattr(content, "text", None)
            if text:
                chunks.append(text)
    return "\n".join(chunks)


def _parse_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))
