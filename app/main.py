from fastapi import FastAPI

from app.api.routes.auth import router as auth_router
from app.api.routes.centres import router as centres_router
from app.api.routes.tests import router as tests_router

app = FastAPI(
    title="CareLabs",
    description="Diagnostic test booking and simulated payment service.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.include_router(auth_router)
app.include_router(centres_router)
app.include_router(tests_router)


@app.get("/health", tags=["Health"], summary="Service health check")
def health() -> dict[str, str]:
    return {"status": "ok"}
