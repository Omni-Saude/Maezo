"""FastAPI application factory for Contract Rule Extraction API."""
from fastapi import FastAPI

from healthcare_platform.contract_extraction.router import router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="MAEZO Contract Rule Extraction API",
        description="Extracts payer contract rules and generates DMN decision tables",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    @app.get("/health")
    async def health() -> dict:
        return {"status": "UP"}

    app.include_router(router)
    return app


app = create_app()
