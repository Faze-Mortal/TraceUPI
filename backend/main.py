from fastapi import FastAPI

from backend.schemas import HealthResponse

app = FastAPI(
    title="TraceUPI API",
    description="Synthetic UPI fraud-ring investigation API",
    version="1.2.0",
)


@app.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok", service="TraceUPI API")
