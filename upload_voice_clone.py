"""上传已授权的声音样本到火山引擎豆包声音复刻 2.0。"""

from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parent
AUDIO_PATH = ROOT / "New Recording 2_clean_24k_mono.wav"
ENV_PATH = ROOT / ".env"
RESPONSE_PATH = ROOT / "voice_clone_response.json"
DEMO_PATH = ROOT / "voice_clone_demo.wav"
ENDPOINT = "https://openspeech.bytedance.com/api/v3/tts/voice_clone"


def load_env(path: Path) -> None:
    """读取简单 KEY=VALUE 配置，不覆盖已经存在的环境变量。"""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> int:
    """提交训练请求，保存接口结果和一小时内有效的试听音频。"""
    load_env(ENV_PATH)
    api_key = os.environ.get("VOLCENGINE_API_KEY", "").strip()
    app_id = os.environ.get("VOLCENGINE_APP_ID", "").strip()
    access_token = os.environ.get("VOLCENGINE_ACCESS_TOKEN", "").strip()
    speaker_id = os.environ.get("VOLCENGINE_SPEAKER_ID", "S_dEYD3fC82").strip()

    using_legacy_auth = bool(app_id and access_token)
    if not using_legacy_auth and (not api_key or api_key.startswith("请粘贴")):
        print(
            "请在 .env 中填写旧版 APP ID + Access Token，或新版 API Key。",
            file=sys.stderr,
        )
        return 2
    if not AUDIO_PATH.exists():
        print(f"找不到音频：{AUDIO_PATH}", file=sys.stderr)
        return 2

    payload = {
        "speaker_id": speaker_id,
        "audio": {
            "data": base64.b64encode(AUDIO_PATH.read_bytes()).decode("ascii"),
            "format": "wav",
        },
        "language": 0,
        "extra_params": {
            # 音频已在本地保守降噪，避免服务端再次降噪损伤声音细节。
            "enable_audio_denoise": False,
            "demo_text": "你好，很高兴认识你。这是一段声音复刻效果测试。",
        },
    }
    auth_headers = (
        {
            "X-Api-App-Key": app_id,
            "X-Api-Access-Key": access_token,
        }
        if using_legacy_auth
        else {"X-Api-Key": api_key}
    )
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Api-Request-Id": str(uuid.uuid4()),
            **auth_headers,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        print(f"上传失败（HTTP {error.code}）：{detail}", file=sys.stderr)
        return 1

    RESPONSE_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"训练状态：{result.get('status')}，"
        f"剩余次数：{result.get('available_training_times')}，"
        f"音色 ID：{result.get('speaker_id', speaker_id)}"
    )

    statuses = result.get("speaker_status") or []
    demo_url = statuses[0].get("demo_audio") if statuses else None
    if demo_url:
        with urllib.request.urlopen(demo_url, timeout=60) as response:
            DEMO_PATH.write_bytes(response.read())
        print(f"试听音频已保存：{DEMO_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
