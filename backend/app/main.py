import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import router
from app.config import REPO_ROOT, load_settings
from app.db import apply_migrations, create_pool, ensure_database
from app.errors import AppError
from app.importer.runner import ImportRunner
from app.logging_config import setup_logging

logger = logging.getLogger(__name__)
DIST_DIR = REPO_ROOT / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    settings = load_settings()
    logger.info("准备数据库", extra={"fields": {"version": "0.1.0"}})
    ensure_database(settings.database_url)
    pool = create_pool(settings.database_url)
    with pool.connection() as conn:
        with conn.transaction():
            apply_migrations(conn)
    app.state.pool = pool
    app.state.settings = settings
    app.state.importer = ImportRunner(pool, settings.resolved_data_root())
    logger.info(
        "服务已启动",
        extra={
            "fields": {
                "host": settings.host,
                "port": settings.port,
                "dataRoot": str(settings.resolved_data_root()),
            }
        },
    )
    yield
    pool.close()
    logger.info("服务已停止")


def create_app() -> FastAPI:
    app = FastAPI(title="门店对账", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def log_api(request: Request, call_next):
        if not request.url.path.startswith("/api"):
            return await call_next(request)
        started = time.perf_counter()
        response = await call_next(request)
        logger.info(
            "request",
            extra={
                "fields": {
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "durationMs": round((time.perf_counter() - started) * 1000, 1),
                }
            },
        )
        return response

    app.include_router(router)
    _register_frontend(app)

    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation(_request: Request, _exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "VALIDATION", "message": "请求参数不正确"}},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, _exc: Exception) -> JSONResponse:
        logger.exception("未处理异常", extra={"fields": {"path": request.url.path}})
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "INTERNAL", "message": "服务器内部错误"}},
        )

    return app


def _register_frontend(app: FastAPI) -> None:
    if not DIST_DIR.is_dir():
        return

    @app.get("/{full_path:path}", include_in_schema=False)
    def frontend(full_path: str) -> FileResponse:
        candidate = _safe_file(DIST_DIR, full_path)
        if candidate is not None:
            return FileResponse(candidate)
        index = DIST_DIR / "index.html"
        if index.is_file():
            return FileResponse(index)
        raise StarletteHTTPException(status_code=404)


def _safe_file(dist: Path, full_path: str) -> Path | None:
    root = dist.resolve()
    candidate = (root / full_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    if candidate.is_file():
        return candidate
    return None


app = create_app()


def main() -> None:
    import uvicorn

    setup_logging()
    settings = load_settings()
    uvicorn.run(app, host=settings.host, port=settings.port, access_log=False, log_config=None)


if __name__ == "__main__":
    main()
