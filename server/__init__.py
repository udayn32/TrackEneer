"""TrackEneer server package marker.

This file makes the `server` directory a Python package so module paths like
`server.app:app` work when running uvicorn from the repository root.
"""

__all__ = ["app", "study", "insights", "placement", "scheduler"]
