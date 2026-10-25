"""Main entry point for Flock Energy Urja Meter Ops API Service."""

import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api import api_v1_router
from app.client.urja_client import UrjaClient
from app.config import settings
from app.services.index_service import index_service

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("flockenergy")

# Shared client instance
urja_client = UrjaClient()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown lifecycle."""
    logger.info("Starting Flock Energy Urja Meter Ops API Service...")
    logger.info(f"Targeting upstream portal: {settings.urja_portal_url}")

    if settings.auto_sync_on_startup:
        try:
            logger.info("Initializing background sync with Urja portal...")
            await index_service.sync(urja_client)
        except Exception as exc:
            logger.warning(
                f"Initial sync warning: {exc}. Service will retry on first request."
            )

    yield

    logger.info("Shutting down API Service...")
    await urja_client.close()


app = FastAPI(
    title="Flock Energy — Urja Meter Ops API Service",
    version="1.0.0",
    description=(
        "A clean, robust, well-documented programmatic REST API service and local index "
        "built over the legacy Urja Meter Ops utility portal. Features normalized meter schemas, "
        "reconstructed electrical network hierarchies, spatial proximity search, and time-series "
        "energy consumption analytics."
    ),
    contact={
        "name": "Flock Energy Engineering Candidate",
        "url": "https://flockenergy.com",
    },
    license_info={
        "name": "Proprietary / Flock Energy Assessment",
    },
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Measure request processing duration and attach X-Process-Time-Ms header."""
    start_time = time.perf_counter()
    response = await call_next(request)
    process_time = (time.perf_counter() - start_time) * 1000.0
    response.headers["X-Process-Time-Ms"] = f"{process_time:.2f}"
    return response


# Include API v1 routes
app.include_router(api_v1_router)

# Root health check alias
from app.api.v1.system import health_check
app.add_api_route("/health", health_check, methods=["GET"], tags=["System"])

# Mount Dashboard UI
STATIC_DIR = Path(__file__).parent / "static"
INDEX_HTML = STATIC_DIR / "index.html"


@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse, tags=["Dashboard"], include_in_schema=False)
@app.api_route("/dashboard", methods=["GET", "HEAD"], response_class=HTMLResponse, tags=["Dashboard"], include_in_schema=False)
async def serve_dashboard():
    """Serve the modern interactive web client dashboard."""
    if INDEX_HTML.exists():
        with open(INDEX_HTML, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h3>Dashboard UI loading...</h3>")
