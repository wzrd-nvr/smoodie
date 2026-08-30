from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy import text

from smoodie_api.config import get_settings
from smoodie_api.db import engine

app = FastAPI(title="smoodie API", version="0.1.0")


class Health(BaseModel):
    status: Literal["ok"]
    env: str
    database: Literal["ok", "unavailable"]


# NOT "/healthz": Cloud Run's Google Frontend intercepts that exact path and
# returns its own 404 before the request reaches the container. Verified against
# the deployed service — every neighbouring path (/health, /livez, /readyz)
# passes through, only /healthz is swallowed.
@app.get("/health", response_model=Health)
async def health() -> Health:
    database: Literal["ok", "unavailable"] = "ok"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        database = "unavailable"
    return Health(status="ok", env=get_settings().env, database=database)
