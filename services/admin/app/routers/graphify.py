"""Admin-backend proxy for the graphify service.

The admin portal's Knowledge Graphs page is browser-side and only holds an admin
session token — it has no gateway sk-* key, and graphify's endpoints require one.
So the page calls these admin routes (gated by the admin session via the
`dependencies=_auth` registration in main.py), and the admin backend forwards to
graphify:8012 with the trusted X-Service-Token (graphify accepts it in place of a
user sk-*). Report/graph.html are returned wrapped in JSON so the portal's
apiFetch (which always parses JSON) can consume them uniformly.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.config import settings

router = APIRouter(prefix="/graphify", tags=["graphify"])

_TIMEOUT = 15.0


def _headers() -> dict:
    return {"X-Service-Token": settings.graphify_service_token}


async def _forward(method: str, path: str, *, params: dict | None = None, json: dict | None = None):
    """Call graphify and return its parsed JSON, mapping errors to HTTPException."""
    url = f"{settings.graphify_url}{path}"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.request(method, url, params=params, json=json, headers=_headers())
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"graphify unreachable: {exc}")
    if resp.status_code >= 400:
        detail = resp.text
        try:
            detail = resp.json().get("detail", detail)
        except Exception:
            pass
        raise HTTPException(status_code=resp.status_code, detail=detail)
    # 204 (delete) has no body.
    if resp.status_code == 204 or not resp.content:
        return {"ok": True}
    return resp.json()


async def _forward_text(path: str, wrap_key: str):
    """Fetch a text artefact (markdown/html) and wrap it as JSON for apiFetch."""
    url = f"{settings.graphify_url}{path}"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, headers=_headers())
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"graphify unreachable: {exc}")
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return {wrap_key: resp.text}


class RepoCreate(BaseModel):
    name: str
    github_url: str | None = None
    ref: str = "main"


@router.get("/repos")
async def list_repos():
    return await _forward("GET", "/repos")


@router.post("/repos", status_code=201)
async def register_repo(body: RepoCreate):
    return await _forward("POST", "/repos", json=body.model_dump())


@router.post("/repos/{name}/rebuild", status_code=202)
async def rebuild_repo(name: str):
    return await _forward("POST", f"/repos/{name}/rebuild")


@router.delete("/repos/{name}", status_code=204)
async def delete_repo(name: str):
    await _forward("DELETE", f"/repos/{name}")


@router.get("/repos/{name}/builds")
async def repo_builds(name: str):
    return await _forward("GET", f"/repos/{name}/builds")


@router.get("/query")
async def query_graph(
    repo: str = Query(...),
    q: str = Query(...),
    budget: int = Query(2000),
    dfs: bool = False,
):
    return await _forward(
        "GET", "/query", params={"repo": repo, "q": q, "budget": budget, "dfs": dfs}
    )


@router.get("/repos/{name}/report")
async def repo_report(name: str):
    return await _forward_text(f"/repos/{name}/report", "markdown")


@router.get("/repos/{name}/graph_html")
async def repo_graph_html(name: str):
    # Path uses graph_html (not graph.html) so it routes cleanly; graphify serves
    # the artefact at /repos/{name}/graph.html.
    return await _forward_text(f"/repos/{name}/graph.html", "html")
