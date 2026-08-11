"""
Placement Module - Backward Compatibility Layer
================================================

Legacy placement routes that delegate to the unified Career Center API.
This file intentionally contains no business logic.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import httpx
from fastapi import FastAPI, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CAREER_API_URL = "http://localhost:5000"


def _forward_headers(request: Request) -> dict[str, str]:
    headers: dict[str, str] = {}
    for key in ("x-user-email", "X-User-Email"):
        if key in request.headers:
            headers[key] = request.headers[key]
    return headers


async def _proxy_request(
    method: str,
    path: str,
    request: Request,
    *,
    params: Optional[dict] = None,
    data: Optional[dict] = None,
) -> JSONResponse:
    url = f"{CAREER_API_URL}{path}"
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.request(
            method,
            url,
            params=params,
            data=data,
            headers=_forward_headers(request),
        )

    try:
        body = response.json()
    except Exception:
        body = {"detail": response.text}

    return JSONResponse(status_code=response.status_code, content=body)


@app.get("/")
def root():
    return {
        "status": "Placement module is running (compatibility mode)",
        "timestamp": datetime.now().isoformat(),
        "mode": "legacy-wrapper",
        "primary_module": "career",
    }


@app.post("/api/placement/generate")
async def generate_placement_info(
    request: Request,
    company_name: str = Form(...),
    website: str = Form(None),
    day: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
):
    formdata: dict[str, str] = {"company_name": company_name}
    if website:
        formdata["website"] = website
    if day:
        formdata["day"] = day
    if email:
        formdata["email"] = email
    return await _proxy_request("POST", "/api/career/companies/generate", request, data=formdata)


@app.get("/api/placement/company/{company_name}")
async def get_company_info(
    company_name: str,
    request: Request,
    day: Optional[str] = None,
    email: Optional[str] = None,
):
    params: dict[str, str] = {}
    if day:
        params["day"] = day
    if email:
        params["email"] = email
    return await _proxy_request("GET", f"/api/career/companies/{company_name}", request, params=params)


@app.get("/api/placement/companies")
async def list_placement_companies(request: Request, day: Optional[str] = None, email: Optional[str] = None):
    params: dict[str, str] = {}
    if day:
        params["day"] = day
    if email:
        params["email"] = email
    return await _proxy_request("GET", "/api/career/companies", request, params=params)


@app.delete("/api/placement/company/{company_name}")
async def delete_company_cache(
    company_name: str,
    request: Request,
    day: Optional[str] = None,
    email: Optional[str] = None,
):
    params: dict[str, str] = {}
    if day:
        params["day"] = day
    if email:
        params["email"] = email
    return await _proxy_request("DELETE", f"/api/career/companies/{company_name}", request, params=params)


@app.get("/api/placement/alumni")
async def get_alumni_data(request: Request):
    return await _proxy_request("GET", "/api/career/alumni", request)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=5003)
