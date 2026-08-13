from app.config import get_settings
from app.services.openai_client import ask_openai_text, openai_status

get_settings.cache_clear()
s = get_settings()
print("model", s.openai_model)
print("key_set", bool((s.openai_api_key or "").strip()))
print("status", openai_status())
try:
    text = ask_openai_text(
        "Reply with JSON only.",
        'Return JSON: {"ok": true, "model": "gpt-5.6-terra", "note": "autovad ping"}',
        temperature=0,
    )
    print("OK_RESPONSE", text[:500])
except Exception as e:
    print("FAIL", type(e).__name__, str(e)[:1200])
