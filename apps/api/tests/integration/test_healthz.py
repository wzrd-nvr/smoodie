import httpx

from smoodie_api.main import app


async def test_healthz_returns_ok() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    # database is "ok" when Postgres is reachable (CI service container),
    # "unavailable" otherwise — both are valid healthz responses.
    assert body["database"] in {"ok", "unavailable"}
