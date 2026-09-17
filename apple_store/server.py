import asyncio
import hmac
import os
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from playwright.async_api import Error as PlaywrightError

from .models import ApiError, Product, Quantity, SessionInput
from .store import StoreSession


def create_app(token: str, factory=StoreSession.create, max_sessions=5):
    if not token:
        raise ValueError("API token required")
    sessions = {}
    creation_lock = asyncio.Lock()

    @asynccontextmanager
    async def lifespan(_app):
        yield
        for session in list(sessions.values()):
            # Finish detached idempotent tasks before closing their browser.
            await asyncio.gather(*(entry[1] for entry in session.idempotency.entries.values()), return_exceptions=True)
            async with session.lock:
                await session.close()
        sessions.clear()

    app = FastAPI(title="Apple 中国商店自动化", lifespan=lifespan)

    @app.middleware("http")
    async def authorize(request: Request, call_next):
        if request.headers.get("origin"):
            response = JSONResponse({"code": "ORIGIN_DENIED"}, status_code=403)
        elif not hmac.compare_digest(request.headers.get("authorization", "").encode(), f"Bearer {token}".encode()):
            response = JSONResponse({"code": "UNAUTHORIZED"}, status_code=401)
        else:
            response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ApiError)
    async def api_error(request, error):
        return JSONResponse({"code": error.code, "message": str(error),
                             "phase": getattr(getattr(request.state, "session", None), "phase", None)},
                            status_code=error.status)

    @app.exception_handler(PlaywrightError)
    async def browser_error(request, _error):
        return JSONResponse({"code": "AUTOMATION_ERROR", "message": "浏览器操作失败，请检查页面、安装和网络",
                             "phase": getattr(getattr(request.state, "session", None), "phase", None)}, status_code=500)

    def get_session(session_id, request):
        session = sessions.get(session_id)
        if session is None:
            raise ApiError("NOT_FOUND", "会话不存在", 404)
        request.state.session = session
        return session

    async def perform(session_id, request, operation, body=None, write=False):
        session = get_session(session_id, request)

        async def action():
            async with session.lock:
                return await operation(session)

        if write:
            return await session.idempotency.run(request.headers.get("idempotency-key"),
                {"method": request.method, "path": request.url.path, "body": body}, action)
        return await action()

    @app.get("/health")
    async def health():
        return {"ok": True, "sessions": len(sessions)}

    @app.post("/sessions", status_code=201)
    async def create_session(options: SessionInput):
        async with creation_lock:
            if len(sessions) >= max_sessions:
                raise ApiError("SESSION_LIMIT", "活跃会话过多", 429)
            session = await factory(options)
            sessions[session.id] = session
        return {"id": session.id, "phase": session.phase}

    @app.get("/sessions/{session_id}")
    async def snapshot(session_id: str, request: Request):
        return await perform(session_id, request, lambda s: s.snapshot())

    @app.put("/sessions/{session_id}/product")
    async def configure(session_id: str, request: Request, product: Product):
        return await perform(session_id, request, lambda s: s.configure(product), product.model_dump(), True)

    @app.post("/sessions/{session_id}/bag/items")
    async def add(session_id: str, request: Request):
        return await perform(session_id, request, lambda s: s.add(), write=True)

    @app.get("/sessions/{session_id}/bag")
    async def bag(session_id: str, request: Request):
        return await perform(session_id, request, lambda s: s.bag())

    @app.patch("/sessions/{session_id}/bag/item")
    async def quantity(session_id: str, request: Request, body: Quantity):
        return await perform(session_id, request, lambda s: s.quantity(body.quantity), body.model_dump(), True)

    @app.post("/sessions/{session_id}/checkout")
    async def checkout(session_id: str, request: Request):
        return await perform(session_id, request, lambda s: s.checkout(), write=True)

    @app.delete("/sessions/{session_id}", status_code=204)
    async def close(session_id: str, request: Request):
        await perform(session_id, request, lambda s: s.close())
        sessions.pop(session_id, None)
        return Response(status_code=204)

    return app


def main():
    import uvicorn
    token = os.getenv("APPLE_API_TOKEN") or secrets.token_hex(24)
    if not os.getenv("APPLE_API_TOKEN"):
        print(f"Temporary API token: {token}", flush=True)
    # One worker, no reload: sessions and idempotency records live in this process.
    uvicorn.run(create_app(token), host="127.0.0.1", port=int(os.getenv("PORT", "3000")), access_log=False)


if __name__ == "__main__":
    main()
