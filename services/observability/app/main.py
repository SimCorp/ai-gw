from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.bus import make_bus
from app.config import settings
from app.router import router
from app.workers import insights, postgres


@asynccontextmanager
async def lifespan(app: FastAPI):
    bus = make_bus(settings)

    pg_handler, pg_pool = await postgres.make_handler(settings.db_url)
    bus.subscribe(pg_handler)
    bus.subscribe(insights.make_handler(settings.appinsights_connection_string))

    await bus.start()
    app.state.bus = bus
    yield
    await bus.stop()
    await pg_pool.close()


app = FastAPI(title="AI Gateway — Observability Service", lifespan=lifespan)
app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok"}
