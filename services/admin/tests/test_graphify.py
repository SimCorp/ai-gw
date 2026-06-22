"""Tests for the admin-backend graphify proxy router.

The portal's Knowledge Graphs page holds only an admin session (no gateway sk-*),
so it calls these admin routes, which forward to graphify:8012 with the trusted
X-Service-Token. These tests verify the forwarding contract: correct upstream
method/path/params, the X-Service-Token header, JSON wrapping of text artefacts,
and error mapping — without a live graphify service.
"""

from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import httpx
import pytest


@contextmanager
def _mock_graphify(*, request=None, get=None):
    """Patch the router's httpx.AsyncClient; return the mock instance for asserts.

    `request` backs _forward (client.request); `get` backs _forward_text (client.get).
    """
    with patch("app.routers.graphify.httpx.AsyncClient") as cls:
        instance = AsyncMock()
        instance.__aenter__.return_value = instance
        if request is not None:
            instance.request.return_value = request
        if get is not None:
            instance.get.return_value = get
        cls.return_value = instance
        yield instance


@pytest.mark.asyncio
async def test_list_repos_proxies_to_graphify(client):
    upstream = httpx.Response(200, json={"repos": [{"name": "ims", "status": "ready"}]})
    with _mock_graphify(request=upstream) as gx:
        resp = await client.get("/graphify/repos")
    assert resp.status_code == 200
    assert resp.json() == {"repos": [{"name": "ims", "status": "ready"}]}
    method, url = gx.request.await_args.args
    assert method == "GET"
    assert url.endswith("/repos")
    assert "X-Service-Token" in gx.request.await_args.kwargs["headers"]


@pytest.mark.asyncio
async def test_register_repo_forwards_body_and_201(client):
    upstream = httpx.Response(201, json={"name": "ims", "status": "registered"})
    with _mock_graphify(request=upstream) as gx:
        resp = await client.post(
            "/graphify/repos", json={"name": "ims", "github_url": None, "ref": "main"}
        )
    assert resp.status_code == 201
    kwargs = gx.request.await_args.kwargs
    assert kwargs["json"] == {"name": "ims", "github_url": None, "ref": "main"}


@pytest.mark.asyncio
async def test_rebuild_proxies_202(client):
    upstream = httpx.Response(202, json={"status": "queued", "build_id": "b1"})
    with _mock_graphify(request=upstream) as gx:
        resp = await client.post("/graphify/repos/ims/rebuild")
    assert resp.status_code == 202
    method, url = gx.request.await_args.args
    assert method == "POST"
    assert url.endswith("/repos/ims/rebuild")


@pytest.mark.asyncio
async def test_delete_repo_returns_204(client):
    upstream = httpx.Response(204)
    with _mock_graphify(request=upstream) as gx:
        resp = await client.delete("/graphify/repos/ims")
    assert resp.status_code == 204
    method, url = gx.request.await_args.args
    assert method == "DELETE"
    assert url.endswith("/repos/ims")


@pytest.mark.asyncio
async def test_query_forwards_params(client):
    upstream = httpx.Response(200, json={"repo": "ims", "result": "subgraph"})
    with _mock_graphify(request=upstream) as gx:
        resp = await client.get(
            "/graphify/query",
            params={"repo": "ims", "q": "where is auth", "budget": 500, "dfs": True},
        )
    assert resp.status_code == 200
    params = gx.request.await_args.kwargs["params"]
    assert params["repo"] == "ims"
    assert params["q"] == "where is auth"
    assert params["budget"] == 500
    assert params["dfs"] is True


@pytest.mark.asyncio
async def test_report_wraps_markdown(client):
    upstream = httpx.Response(200, text="# Graph report\n")
    with _mock_graphify(get=upstream) as gx:
        resp = await client.get("/graphify/repos/ims/report")
    assert resp.status_code == 200
    assert resp.json() == {"markdown": "# Graph report\n"}
    (url,) = gx.get.await_args.args
    assert url.endswith("/repos/ims/report")


@pytest.mark.asyncio
async def test_graph_html_wraps_html_from_dotted_upstream(client):
    upstream = httpx.Response(200, text="<html></html>")
    with _mock_graphify(get=upstream) as gx:
        resp = await client.get("/graphify/repos/ims/graph_html")
    assert resp.status_code == 200
    assert resp.json() == {"html": "<html></html>"}
    # Clean route is /graph_html, but graphify serves the artefact at /graph.html.
    (url,) = gx.get.await_args.args
    assert url.endswith("/repos/ims/graph.html")


@pytest.mark.asyncio
async def test_upstream_error_propagates_status_and_detail(client):
    upstream = httpx.Response(409, json={"detail": "graph not built yet"})
    with _mock_graphify(request=upstream):
        resp = await client.get("/graphify/query", params={"repo": "ims", "q": "x"})
    assert resp.status_code == 409
    assert resp.json()["detail"] == "graph not built yet"


@pytest.mark.asyncio
async def test_graphify_unreachable_returns_502(client):
    with patch("app.routers.graphify.httpx.AsyncClient") as cls:
        instance = AsyncMock()
        instance.__aenter__.return_value = instance
        instance.request.side_effect = httpx.ConnectError("refused")
        cls.return_value = instance
        resp = await client.get("/graphify/repos")
    assert resp.status_code == 502
    assert "unreachable" in resp.json()["detail"]
