"""Unified FastAPI application consolidating TrackEneer services behind one server."""
from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from db import close_driver
from insights import app as insights_app
from placement import app as placement_app
from scheduler import app as scheduler_app
from study import app as study_app

ALLOWED_ORIGINS = ["http://localhost:3000"]

app = FastAPI(title="TrackEneer Unified API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _propagate_lifespan_events(source_app: FastAPI, target_app: FastAPI) -> None:
    """Copy startup/shutdown event handlers from one FastAPI app into another."""
    for handler in source_app.router.on_startup:
        target_app.add_event_handler("startup", handler)
    for handler in source_app.router.on_shutdown:
        target_app.add_event_handler("shutdown", handler)


def _remove_conflicting_root_routes(source_app: FastAPI) -> None:
    """Drop `GET /` routes to avoid duplicate health endpoints when combining apps."""
    filtered_routes = []
    for route in source_app.router.routes:
        if getattr(route, "path", None) == "/" and "GET" in getattr(route, "methods", set()):
            continue
        filtered_routes.append(route)
    source_app.router.routes[:] = filtered_routes


def _include_app(source_app: FastAPI, *, prefix: str | None = None) -> None:
    """Include routes and lifespan handlers from a source FastAPI application."""
    _remove_conflicting_root_routes(source_app)
    if prefix:
        app.include_router(source_app.router, prefix=prefix)
    else:
        app.include_router(source_app.router)
    _propagate_lifespan_events(source_app, app)


_include_app(scheduler_app)
_include_app(study_app)
_include_app(insights_app)
_include_app(placement_app)


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.on_event("shutdown")
async def shutdown_driver() -> None:
    close_driver()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT", 5000)), reload=False)
