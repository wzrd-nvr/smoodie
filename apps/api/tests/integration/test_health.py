import httpx

from smoodie_api.main import app


async def test_health_returns_ok() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    # database is "ok" when Postgres is reachable (CI service container),
    # "unavailable" otherwise — both are valid health responses.
    assert body["database"] in {"ok", "unavailable"}


def test_no_route_is_named_healthz() -> None:
    """Cloud Run's frontend swallows /healthz before it reaches the container.

    Checked against the published OpenAPI paths rather than app.routes, which
    holds router objects without a .path once include_router is used.
    """
    paths = set(app.openapi()["paths"])
    assert "/health" in paths
    assert "/healthz" not in paths
