import json, os

class ConfigManager:
    def __init__(self):
        self.path = 'config.json'
        self.config = self.load()

    def load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except: pass
        return {
            "naver_client_id": "", "naver_client_secret": "",
            "telegram_token": "", "telegram_chat_id": "",
            "keywords": ["단독"], "exclude_keywords": [], "check_interval": 60
        }

    def save(self):
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=4, ensure_ascii=False)
