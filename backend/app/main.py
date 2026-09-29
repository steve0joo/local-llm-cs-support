from fastapi import FastAPI

from app.agents import balance, interest, loan
from app.gateway.api import router as chat_router


def create_app() -> FastAPI:
    app = FastAPI(title="로컬 LLM 은행 csSupport")
    app.include_router(chat_router)
    for package in (balance, loan, interest):
        app.include_router(package.mock_router)
    return app


app = create_app()
