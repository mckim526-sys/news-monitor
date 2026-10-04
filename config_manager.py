import copy
import json
import logging
import os
import tempfile
import threading
from pathlib import Path

class ConfigManager:
    def __init__(self):
        self.lock = threading.RLock()
        self.path = Path(os.environ.get("CONFIG_PATH", Path(__file__).with_name("config.json")))
        self.config = self.load()

    def load(self):
        defaults = {"naver_client_id": "", "naver_client_secret": "", "telegram_token": "", "telegram_chat_id": "", "keywords": ['"국민의힘"', '"국힘"'], "exclude_keywords": [], "check_interval": 60, "start_hour": 0, "end_hour": 24, "photo_min_chars": 120}
        if self.path.exists():
            with self.path.open(encoding="utf-8") as f:
                saved = json.load(f)  # 손상된 설정을 빈 기본값으로 덮어쓰지 않습니다.
            if not isinstance(saved, dict):
                raise ValueError("config.json은 JSON 객체여야 합니다.")
            defaults.update(saved)
        for key in ("keywords", "exclude_keywords"):
            if not isinstance(defaults[key], list) or any(not isinstance(x, str) for x in defaults[key]):
                raise ValueError(f"{key}는 문자열 목록이어야 합니다.")
        for key, low, high in (("check_interval", 10, 86400), ("start_hour", 0, 23), ("end_hour", 0, 24), ("photo_min_chars", 0, 10000)):
            value = int(defaults[key])
            if not low <= value <= high:
                raise ValueError(f"{key}: {low}~{high} 범위 필요")
            defaults[key] = value
        return defaults

    def snapshot(self):
        with self.lock:
            config = copy.deepcopy(self.config)
        for key in ("naver_client_id", "naver_client_secret", "telegram_token", "telegram_chat_id"):
            config[key] = os.environ.get(key.upper(), config.get(key, ""))
        return config

    def save(self):
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            name = None
            try:
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent, delete=False) as f:
                    name = f.name
                    json.dump(self.config, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(name, self.path)
            finally:
                if name and os.path.exists(name):
                    os.unlink(name)

    def change(self, callback):
        with self.lock:
            old = copy.deepcopy(self.config)
            try:
                callback(self.config)
                self.save()
            except Exception:
                self.config = old
                raise
