import mimetypes
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import router
from .config import FRONTEND_DIST
from .db import Bot, SessionLocal, init_db
from .platforms import resume_all

# Windows registries sometimes map .js to text/plain, which browsers refuse for module scripts.
for _ext, _type in ((".js", "application/javascript"), (".css", "text/css"), (".woff2", "font/woff2"), (".woff", "font/woff")):
    mimetypes.add_type(_type, _ext)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with SessionLocal() as db:  # an agent run interrupted by a restart must not stay "running"
        db.query(Bot).filter(Bot.agent_status == "running").update({"agent_status": "idle"})
        db.commit()
    threading.Thread(target=resume_all, daemon=True).start()
    yield


app = FastAPI(title="BotLab", lifespan=lifespan)
app.include_router(router)

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith(("api/", "hook/")):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        root = FRONTEND_DIST.resolve()
        f = (root / path).resolve()
        if path and f.is_relative_to(root) and f.is_file():
            return FileResponse(f)
        return FileResponse(FRONTEND_DIST / "index.html")
