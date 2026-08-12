"""LokalReader FastAPI application."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from lokalreader import config
from lokalreader.api.routes import router

config.ensure_dirs()

app = FastAPI(
    title="LokalReader",
    description="Free, local, non-subscription book reader that speaks books aloud.",
    version="0.1.0",
)
app.include_router(router)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(config.FRONTEND_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(config.FRONTEND_DIR)), name="static")
