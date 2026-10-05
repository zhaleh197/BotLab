import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# Some Windows setups point SSL_CERT_FILE at a non-certificate file (e.g. openssl.cnf), which breaks
# every HTTPS call. Ignore it unless it really is a PEM bundle, so the bundled certifi CAs are used.
_cert = os.getenv("SSL_CERT_FILE")
if _cert:
    try:
        _ok = "BEGIN CERTIFICATE" in Path(_cert).read_text(errors="ignore")[:200000]
    except OSError:
        _ok = False
    if not _ok:
        os.environ.pop("SSL_CERT_FILE", None)


def _db_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        return f"sqlite:///{BASE_DIR / 'data.db'}"
    # Neon / Render give postgres:// or postgresql:// — use the psycopg3 driver.
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


DATABASE_URL = _db_url()
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_DAYS = 14

# Any OpenAI-compatible provider: Gemini (default), Groq, OpenRouter, ...
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-3.5-flash")
# Tried in order when the main model is overloaded or rate-limited (comma separated).
LLM_FALLBACK_MODELS = os.getenv("LLM_FALLBACK_MODELS", "gemini-flash-latest,gemini-3.5-flash-lite")
LLM_MODELS = [LLM_MODEL] + [m.strip() for m in LLM_FALLBACK_MODELS.split(",") if m.strip() and m.strip() != LLM_MODEL]

# Public base URL used for bot webhooks. Render sets RENDER_EXTERNAL_URL automatically.
# When empty, published bots run in long-polling mode (handy for local development).
PUBLIC_URL = (os.getenv("PUBLIC_URL") or os.getenv("RENDER_EXTERNAL_URL") or "").rstrip("/")

FRONTEND_DIST = Path(os.getenv("FRONTEND_DIST", BASE_DIR.parent / "frontend" / "dist"))
TIMEZONE = os.getenv("BOT_TIMEZONE", "Asia/Tehran")
