from contextlib import asynccontextmanager
import json
from pathlib import Path
import secrets
from urllib.parse import urlparse
from uuid import UUID
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from .config import Settings
from .store import Store, Missing, Busy
from .service import Agent
from .model import Model
from .providers import Providers
from .demo import DemoModel, DemoProviders


class Chat(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=3000)
    conversation_id: UUID | None = None


def create_app(cfg=None, model=None, providers=None):
    cfg = cfg or Settings()

    @asynccontextmanager
    async def lifespan(app):
        cfg.validate()
        m = model or (DemoModel() if cfg.mode == "demo" else Model(cfg))
        p = providers or (DemoProviders() if cfg.mode == "demo" else Providers(cfg))
        app.state.agent = Agent(cfg, Store(cfg.database), m, p)
        try:
            yield
        finally:
            await m.close()
            await p.close()

    app = FastAPI(title="Activities Advisor · Clip 2", lifespan=lifespan)
    web = Path(__file__).parent / "web"
    app.mount("/static", StaticFiles(directory=web), name="static")

    @app.middleware("http")
    async def local_guard(request, call_next):
        # This local lab has no login screen. Refuse public hostnames and cross-origin writes.
        if request.url.hostname not in {
            "localhost",
            "127.0.0.1",
            "[::1]",
            "::1",
            "testserver",
        }:
            return JSONResponse(
                {"detail": "Local baseline: use localhost or 127.0.0.1."},
                status_code=403,
            )
        origin = request.headers.get("origin")
        if (
            request.method == "POST"
            and origin
            and origin != str(request.base_url).rstrip("/")
        ):
            return JSONResponse(
                {"detail": "Cross-origin requests are not allowed."}, status_code=403
            )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        return response

    def owner(request):
        token = request.cookies.get("advisor_session", "")
        if len(token) < 32 or len(token) > 100:
            raise HTTPException(401, "Open the planning page to start a session.")
        return token

    @app.get("/")
    def index(request: Request):
        response = FileResponse(web / "index.html")
        token = request.cookies.get("advisor_session", "")
        if len(token) < 32 or len(token) > 100:
            response.set_cookie(
                "advisor_session",
                secrets.token_urlsafe(32),
                httponly=True,
                samesite="strict",
                max_age=86400,
            )
        return response

    @app.get("/api/config")
    def config():
        return {
            "mode": cfg.mode,
            "stage": "clip2",
            "model": cfg.model if cfg.mode == "live" else "offline fixture",
        }

    @app.get("/healthz")
    def health():
        return {"status": "ok", "mode": cfg.mode}

    @app.post("/api/chat")
    async def chat(body: Chat, request: Request):
        if not body.message.strip():
            raise HTTPException(422, "Enter a request.")
        identity = owner(request)
        agent = request.app.state.agent
        cid = (
            str(body.conversation_id)
            if body.conversation_id
            else agent.store.create(identity)
        )
        try:
            history, state, lease = agent.store.acquire(cid, identity)
        except Missing:
            raise HTTPException(404, "Conversation not found. Start a new trip.")
        except Busy as exc:
            raise HTTPException(409, str(exc))

        async def stream():
            try:
                async for event in agent.stream(
                    cid, identity, body.message, history, state, lease
                ):
                    yield json.dumps(event) + "\n"
            finally:
                agent.store.release(cid, lease)

        return StreamingResponse(
            stream(),
            media_type="application/x-ndjson",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/runs/{rid}")
    def run(rid: str, request: Request):
        try:
            return request.app.state.agent.store.run(rid, owner(request))
        except Missing:
            raise HTTPException(404, "Run not found")

    return app


app = create_app()
