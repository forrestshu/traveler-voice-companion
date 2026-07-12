"""火山实时语音适配层：负责云端二进制协议与本地网页事件之间的转换。"""

from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import suppress

import websockets
from fastapi import WebSocket, WebSocketDisconnect
from volcengine_audio import (
    EventReceive,
    RealtimeDialogueConfig,
    RealtimeDialogueFunctions,
    VolcengineTTSFunctions,
)

from backend.config import Settings
from backend.prompts import PAIMON_CHARACTER_MANIFEST


def build_dialogue_config(settings: Settings) -> RealtimeDialogueConfig:
    """构造 SC2.0 会话配置，输入为浏览器 PCM，输出为复刻音色 PCM。"""
    return RealtimeDialogueConfig(
        dialog=RealtimeDialogueConfig.DialogConfig(
            bot_name="派蒙",
            character_manifest=PAIMON_CHARACTER_MANIFEST,
            extra=RealtimeDialogueConfig.DialogConfig.Extra(
                model=RealtimeDialogueConfig.DialogConfig.Extra.Model.model_sc2_0,
                input_mod=RealtimeDialogueConfig.DialogConfig.Extra.InputMod.audio,
                enable_conversation_truncate=True,
            ),
        ),
        asr=RealtimeDialogueConfig.Asr(
            audio_info=RealtimeDialogueConfig.Asr.AudioInfo(
                format=RealtimeDialogueConfig.Asr.AudioInfo.Format.pcm,
                sample_rate=16000,
                channel=1,
            ),
            extra=RealtimeDialogueConfig.Asr.Extra(
                end_smooth_window_ms=900,
                enable_asr_twopass=True,
            ),
        ),
        tts=RealtimeDialogueConfig.TTSConfig(
            speaker=settings.realtime_speaker_id,
            audio_config=RealtimeDialogueConfig.TTSConfig.AudioConfig(
                format=RealtimeDialogueConfig.TTSConfig.AudioConfig.Format.pcm_s16le,
                sample_rate=24000,
                channel=1,
            ),
        ),
    )


async def _send_ui(websocket: WebSocket, event: str, **payload: object) -> None:
    """向浏览器发送结构化状态；音频数据则走独立的二进制消息。"""
    await websocket.send_text(json.dumps({"event": event, **payload}, ensure_ascii=False))


async def _browser_to_cloud(
    browser: WebSocket,
    cloud: websockets.ClientConnection,
    session_id: str,
) -> None:
    """上行数据流：把浏览器的 16 kHz PCM 和控制命令发送给火山引擎。"""
    while True:
        message = await browser.receive()
        if message.get("bytes") is not None:
            audio = message["bytes"]
            if audio:
                await cloud.send(
                    RealtimeDialogueFunctions.task_request_payload(session_id, audio)
                )
            continue

        if message.get("text"):
            command = json.loads(message["text"])
            if command.get("type") == "interrupt":
                await cloud.send(
                    RealtimeDialogueFunctions.client_interrupt_payload(session_id)
                )
            elif command.get("type") == "finish":
                await cloud.send(
                    RealtimeDialogueFunctions.finish_session_payload(session_id)
                )
                return
        if message.get("type") == "websocket.disconnect":
            return


async def _cloud_to_browser(
    browser: WebSocket,
    cloud: websockets.ClientConnection,
) -> None:
    """下行数据流：解包云端事件，把字幕、状态与 24 kHz PCM 分发给网页。"""
    async for packet in cloud:
        if not isinstance(packet, bytes):
            continue
        event, _session_id, payload = VolcengineTTSFunctions.extract_response_payload(packet)

        if event == EventReceive.TTSResponse:
            await browser.send_bytes(payload)
        elif event == EventReceive.ASRInfo:
            await _send_ui(browser, "status", value="listening")
        elif event == EventReceive.ASRResponse:
            results = payload.get("results", []) if isinstance(payload, dict) else []
            if results:
                latest = results[-1]
                await _send_ui(
                    browser,
                    "transcript",
                    role="traveler",
                    text=latest.get("text", ""),
                    interim=latest.get("is_interim", True),
                )
        elif event == EventReceive.ASREnded:
            await _send_ui(browser, "status", value="thinking")
        elif event == EventReceive.ChatResponse:
            await _send_ui(
                browser,
                "transcript",
                role="paimon",
                text=payload.get("content", "") if isinstance(payload, dict) else "",
                interim=True,
            )
        elif event == EventReceive.ChatEnded:
            await _send_ui(browser, "transcript_end", role="paimon")
        elif event == EventReceive.TTSSentenceStart:
            await _send_ui(browser, "status", value="speaking")
        elif event == EventReceive.TTSEnded:
            await _send_ui(browser, "status", value="listening")
        elif event == EventReceive.USAGE:
            await _send_ui(browser, "usage", data=payload)
        elif event in (
            EventReceive.DialogCommonError,
            EventReceive.SessionFailed,
            EventReceive.ConnectionFailed,
        ):
            await _send_ui(browser, "error", message=str(payload))
            return


async def run_realtime_session(browser: WebSocket, settings: Settings) -> None:
    """会话总控：鉴权建连、启动 SC2.0，再并发桥接浏览器和火山引擎。"""
    connect_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    headers = {
        "X-Api-App-ID": settings.app_id,
        "X-Api-Access-Key": settings.access_token,
        "X-Api-Resource-Id": settings.realtime_resource_id,
        "X-Api-App-Key": settings.realtime_app_key,
        "X-Api-Connect-Id": connect_id,
    }

    try:
        async with websockets.connect(
            settings.realtime_url,
            additional_headers=headers,
            max_size=None,
            ping_interval=20,
        ) as cloud:
            await cloud.send(RealtimeDialogueFunctions.start_connection_payload())
            connection_packet = await asyncio.wait_for(cloud.recv(), timeout=15)
            event, _, payload = VolcengineTTSFunctions.extract_response_payload(
                connection_packet
            )
            if event != EventReceive.ConnectionStarted:
                raise RuntimeError(f"实时服务建连失败：{payload}")

            await cloud.send(
                RealtimeDialogueFunctions.start_session_payload(
                    session_id, build_dialogue_config(settings)
                )
            )
            session_packet = await asyncio.wait_for(cloud.recv(), timeout=20)
            event, _, payload = VolcengineTTSFunctions.extract_response_payload(
                session_packet
            )
            if event != EventReceive.SessionStarted:
                raise RuntimeError(f"实时会话启动失败：{payload}")

            await _send_ui(
                browser, "ready", speaker_id=settings.realtime_speaker_id
            )
            upstream = asyncio.create_task(
                _browser_to_cloud(browser, cloud, session_id)
            )
            downstream = asyncio.create_task(_cloud_to_browser(browser, cloud))
            done, pending = await asyncio.wait(
                {upstream, downstream}, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            for task in done:
                task.result()
            with suppress(Exception):
                await cloud.send(
                    RealtimeDialogueFunctions.finish_connection_payload()
                )
    except WebSocketDisconnect:
        return
    except Exception as error:
        with suppress(Exception):
            await _send_ui(browser, "error", message=str(error))
