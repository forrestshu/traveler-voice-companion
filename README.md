# 旅途回声

一个在本机运行的实时语音陪伴对话应用。浏览器采集麦克风音频，FastAPI 在本机保管火山引擎凭证并代理实时 WebSocket，SC2.0 模型使用专用复刻音色回复。

## 本地启动

打开两个终端窗口。

后端：

```bash
uv run uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload
```

前端：

```bash
pnpm -C frontend dev
```

然后访问 <http://127.0.0.1:5173>，点击“开始对话”并允许麦克风权限。

## 配置边界

- `.env` 包含长期凭证，已被 `.gitignore` 排除，禁止提交或放入前端。
- `VOLCENGINE_SPEAKER_ID` 是普通 TTS 2.0 音色。
- `VOLCENGINE_REALTIME_SPEAKER_ID` 是实时 SC2.0 专用音色。
- 视频默认静音，避免和 AI 回复音频冲突。

## 验证

```bash
pnpm -C frontend exec tsc -b --pretty false
pnpm -C frontend build
uv run python -m compileall -q backend
```

