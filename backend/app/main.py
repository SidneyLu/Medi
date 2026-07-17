from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import get_store
from app.api.routes import auth, chat, content, health, knowledge, profile, reports
from app.core.config import get_settings
from app.core.responses import install_exception_handlers


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Medi 家用医疗健康 RAG WebApp 第一阶段后端",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    install_exception_handlers(app)

    app.include_router(health.router, prefix=settings.api_prefix)
    app.include_router(auth.router, prefix=settings.api_prefix)
    app.include_router(profile.router, prefix=settings.api_prefix)
    app.include_router(knowledge.router, prefix=settings.api_prefix)
    app.include_router(content.router, prefix=settings.api_prefix)
    app.include_router(chat.router, prefix=settings.api_prefix)
    app.include_router(reports.router, prefix=settings.api_prefix)

    @app.on_event("startup")
    def startup() -> None:
        get_store().initialize()

    return app


app = create_app()
