import logging
import os
import sqlite3
import threading
import time
from pathlib import Path
from io import BytesIO
import pandas as pd
import requests
from news_utils import article_info, clean_title, is_scoop, AGENCIES, PAPERS, BROADCASTS

class DataHandler:
    def __init__(self, state_path=None):
        self.lock = threading.RLock()
        self.sheet_lock = threading.Lock()
        self.logs = {key: [] for key in ("scoops", "mbc", "agencies", "papers", "broadcasts", "logs")}
        self.history = set()
        self.sheet = None
        self.sheet_time = 0
        self.EXPORT_URL = "https://docs.google.com/spreadsheets/d/1Mi5gxnKG0Z6l-beesiVdrR2tey7qfIL6LqyNF1slHww/gviz/tq?tqx=out:csv&gid=1727539678"
        path = Path(state_path or os.environ.get("STATE_PATH", Path(__file__).with_name("state.sqlite3")))
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.execute("CREATE TABLE IF NOT EXISTS alerts (id TEXT PRIMARY KEY, title TEXT NOT NULL, url TEXT NOT NULL, sent INTEGER NOT NULL DEFAULT 0)")
        self.conn.commit()

    def snapshot(self):
        with self.lock:
            return {key: list(rows) for key, rows in self.logs.items()}

    def seen(self, item):
        info = article_info(item.get("link", ""))
        with self.lock:
            return not info or info[2] in self.history

    def classify(self, item, media, p_date):
        info = article_info(item.get("link", ""))
        if not info:
            return False
        oid, _, key, url = info
        title = clean_title(item.get("title", ""))
        target = "mbc" if oid == "214" else "agencies" if oid in AGENCIES else "papers" if oid in PAPERS else "broadcasts" if oid in BROADCASTS else "logs"
        obj = {"media": media, "title": title, "url": url, "dt": p_date, "display_time": p_date.strftime("%H:%M")}
        with self.lock:
            if key in self.history:
                return False
            if is_scoop(title):
                self.conn.execute("INSERT OR IGNORE INTO alerts(id,title,url) VALUES(?,?,?)", (key, title, url))
                self.conn.commit()
            for bucket in ([target, "scoops"] if is_scoop(title) else [target]):
                self.logs[bucket].append(obj)
                self.logs[bucket].sort(key=lambda x: x["dt"], reverse=True)
                del self.logs[bucket][100:]
            self.history.add(key)
            # 화면 중복 이력은 크기를 제한하고 알림 이력은 SQLite에 보존합니다.
            if len(self.history) > 20000:
                self.history = {article_info(row["url"])[2] for rows in self.logs.values() for row in rows}
        return True

    def pending_alerts(self):
        with self.lock:
            return self.conn.execute("SELECT id,title,url FROM alerts WHERE sent=0 LIMIT 20").fetchall()

    def mark_sent(self, key):
        with self.lock:
            self.conn.execute("UPDATE alerts SET sent=1 WHERE id=?", (key,))
            self.conn.commit()

    def clear_all(self):
        with self.lock:
            for rows in self.logs.values():
                rows.clear()
            self.history.clear()  # 알림 이력은 유지하므로 RESET 후 재알림을 방지합니다.

    def search_sheet_data(self, query):
        if not query.strip():
            return []
        with self.sheet_lock:
            if self.sheet is None or time.monotonic() - self.sheet_time > 300:
                response = requests.get(self.EXPORT_URL, timeout=(3, 8))
                response.raise_for_status()
                self.sheet = pd.read_csv(BytesIO(response.content), dtype=str).fillna("")
                self.sheet_time = time.monotonic()
            df = self.sheet
            mask = df.apply(lambda row: row.str.contains(query, case=False, regex=False, na=False).any(), axis=1)
            return [{"name": row.get("성명", "미상"), "party": row.get("정당", "미상"), "dist": row.get("선거구", "미상"), "tel": row.get("연락처", "미상")} for _, row in df[mask].head(100).iterrows()]
