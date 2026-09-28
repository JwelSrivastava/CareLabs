from fastapi import FastAPI

app = FastAPI(
    title="CareLabs",
    description="Diagnostic test booking and simulated payment service.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)


@app.get("/health", tags=["Health"], summary="Service health check")
def health() -> dict[str, str]:
    return {"status": "ok"}
