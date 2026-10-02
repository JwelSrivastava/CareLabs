from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes.auth import router as auth_router
from app.api.routes.bookings import router as bookings_router
from app.api.routes.centres import router as centres_router
from app.api.routes.payments import router as payments_router
from app.api.routes.tests import router as tests_router

app = FastAPI(
    title="CareLabs",
    description="Diagnostic test booking and simulated payment service.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.include_router(auth_router)
app.include_router(bookings_router)
app.include_router(centres_router)
app.include_router(payments_router)
app.include_router(tests_router)


@app.get("/health", tags=["Health"], summary="Service health check")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def home() -> RedirectResponse:
    return RedirectResponse(url="/ui/")


_web_dir = Path(__file__).resolve().parents[1] / "web"
if _web_dir.is_dir():
    app.mount("/ui", StaticFiles(directory=_web_dir, html=True), name="ui")
