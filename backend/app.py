"""FastAPI 入口层：提供健康检查、WebSocket 代理和生产静态资源。"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.config import ROOT, Settings
from backend.realtime import run_realtime_session


app = FastAPI(title="旅行者实时语音伙伴")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict[str, object]:
    """健康检查接口：只返回是否配置完成，不泄露任何真实凭证。"""
    try:
        settings = Settings.from_env()
        return {"ok": True, "speaker_id": settings.realtime_speaker_id}
    except RuntimeError as error:
        return {"ok": False, "message": str(error)}


@app.websocket("/ws/conversation")
async def conversation(websocket: WebSocket) -> None:
    """浏览器会话入口：接受连接后把音频流交给火山引擎适配层。"""
    try:
        settings = Settings.from_env()
    except RuntimeError as error:
        await websocket.accept()
        await websocket.send_json({"event": "error", "message": str(error)})
        await websocket.close(code=1011)
        return

    # 安全边界：WebSocket 不受普通 CORS 中间件保护，必须显式校验 Origin。
    origin = websocket.headers.get("origin", "")
    if origin not in settings.allowed_origins:
        await websocket.close(code=1008, reason="Origin not allowed")
        return

    await websocket.accept()
    await run_realtime_session(websocket, settings)


DIST = ROOT / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    async def frontend(path: str) -> FileResponse:
        """生产模式回退：未知路径统一返回 React 单页入口。"""
        candidate = DIST / path
        if path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(DIST / "index.html")
