import asyncio
import os

import uvicorn


def _env_truthy(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


if __name__ == "__main__":
    # On Windows + Python 3.14, reload mode can emit noisy CancelledError tracebacks
    # during Ctrl+C shutdown even when requests succeed. Default to clean shutdown.
    reload_enabled = _env_truthy("AUTOVAD_RELOAD", default=False)
    # Long keep-alive so analyze/upload connections are not dropped while waiting on OpenAI/APS.
    try:
        uvicorn.run(
            "app.main:app",
            host="127.0.0.1",
            port=8001,
            reload=reload_enabled,
            timeout_keep_alive=86400,
        )
    except (KeyboardInterrupt, asyncio.CancelledError):
        # Graceful local shutdown; suppress shutdown traceback noise.
        pass
