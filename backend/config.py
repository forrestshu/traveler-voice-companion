"""系统配置层：集中读取本机密钥，避免长期凭证进入浏览器。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _load_env(path: Path) -> None:
    """读取项目根目录的简单 .env 文件，不覆盖进程已有环境变量。"""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    """后端运行配置：只在服务端内存中保存火山引擎凭证。"""

    app_id: str
    access_token: str
    speaker_id: str
    realtime_speaker_id: str
    allowed_origins: tuple[str, ...]
    realtime_url: str = "wss://openspeech.bytedance.com/api/v3/realtime/dialogue"
    realtime_resource_id: str = "volc.speech.dialog"
    realtime_app_key: str = "PlgvMymc7f3tQnJ6"

    @classmethod
    def from_env(cls) -> "Settings":
        """加载并校验实时语音服务所需的三个用户配置。"""
        _load_env(ROOT / ".env")
        settings = cls(
            app_id=os.environ.get("VOLCENGINE_APP_ID", "").strip(),
            access_token=os.environ.get("VOLCENGINE_ACCESS_TOKEN", "").strip(),
            speaker_id=os.environ.get("VOLCENGINE_SPEAKER_ID", "").strip(),
            realtime_speaker_id=os.environ.get(
                "VOLCENGINE_REALTIME_SPEAKER_ID", ""
            ).strip(),
            allowed_origins=tuple(
                origin.strip()
                for origin in os.environ.get(
                    "ALLOWED_ORIGINS",
                    "http://127.0.0.1:5173,http://localhost:5173,"
                    "https://traveler-voice-companion-fengyuan.netlify.app",
                ).split(",")
                if origin.strip()
            ),
        )
        missing = [
            name
            for name, value in (
                ("VOLCENGINE_APP_ID", settings.app_id),
                ("VOLCENGINE_ACCESS_TOKEN", settings.access_token),
                ("VOLCENGINE_SPEAKER_ID", settings.speaker_id),
                (
                    "VOLCENGINE_REALTIME_SPEAKER_ID",
                    settings.realtime_speaker_id,
                ),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(f".env 缺少配置：{', '.join(missing)}")
        return settings
