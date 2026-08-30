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


@app.get("/healthz", response_model=Health)
async def healthz() -> Health:
    database: Literal["ok", "unavailable"] = "ok"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        database = "unavailable"
    return Health(status="ok", env=get_settings().env, database=database)
