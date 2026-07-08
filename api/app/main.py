from fastapi import FastAPI

from app.core.config import get_settings
from app.db.base import init_db
from app.routers import admin, chat, compare, health, products, sources

settings = get_settings()
app = FastAPI(title=settings.app_name)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


app.include_router(health.router)
app.include_router(products.router)
app.include_router(compare.router)
app.include_router(chat.router)
app.include_router(admin.router)
app.include_router(sources.router)
