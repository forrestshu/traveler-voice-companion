"""把已授权录音注册到端到端实时语音 SC2.0 专用音色槽位。"""

from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from backend.config import ROOT, Settings, _load_env


AUDIO_PATH = ROOT / "New Recording 2_clean_24k_mono.wav"
RESPONSE_PATH = ROOT / "realtime_voice_registration.json"
ENDPOINT = "https://openspeech.bytedance.com/api/v1/mega_tts/audio/upload"


def main() -> int:
    """提交 SC2.0 注册请求；输入文本必须与录音内容一致。"""
    _load_env(ROOT / ".env")
    settings = Settings.from_env()
    prompt_text = os.environ.get("VOLCENGINE_REALTIME_PROMPT_TEXT", "").strip()
    if not prompt_text or prompt_text.startswith("请填写"):
        print(
            "请先在 .env 填写 VOLCENGINE_REALTIME_PROMPT_TEXT。",
            file=sys.stderr,
        )
        return 2
    if not AUDIO_PATH.exists():
        print(f"找不到训练音频：{AUDIO_PATH}", file=sys.stderr)
        return 2

    payload = {
        "speaker_id": settings.realtime_speaker_id,
        "appid": settings.app_id,
        "audios": [
            {
                "audio_bytes": base64.b64encode(AUDIO_PATH.read_bytes()).decode(
                    "ascii"
                ),
                "text": prompt_text,
                "audio_format": "wav",
            }
        ],
        "model_type": 4,
        "source": 2,
    }
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer; {settings.access_token}",
            "Resource-Id": "seed-icl-2.0",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        print(f"实时音色注册失败（HTTP {error.code}）：{detail}", file=sys.stderr)
        return 1

    RESPONSE_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"实时音色状态：{result.get('status')}，"
        f"音色 ID：{result.get('speaker_id', settings.realtime_speaker_id)}，"
        f"剩余次数：{result.get('available_training_times')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
