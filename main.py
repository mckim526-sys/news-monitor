import html
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import requests
from flask import Flask, render_template, request, jsonify, redirect, url_for, abort
from config_manager import ConfigManager
from news_engine import NewsEngine
from data_handler import DataHandler
from news_utils import article_info, clean_title, is_photo

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
app = Flask(__name__)
cfg = ConfigManager()
engine = NewsEngine()
db = DataHandler()
KST = timezone(timedelta(hours=9))
state_lock = threading.Lock()
worker_lock = threading.Lock()
wake = threading.Event()
worker_started = False
LAST_UPDATE_TIME = "--:--:--"
STATUS = "수집 대기"

def set_status(status, successful=False):
    global LAST_UPDATE_TIME, STATUS
    with state_lock:
        STATUS = status
        if successful:
            LAST_UPDATE_TIME = datetime.now(KST).strftime("%H:%M:%S")

def active_hour(hour, config):
    start, end = config["start_hour"], config["end_hour"]
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end if start != end else True

def send_telegram(title, link, config):
    token, chat_id = config.get("telegram_token"), config.get("telegram_chat_id")
    if not token or not chat_id:
        return False
    text = f'🚨 <b>[단독]</b>\n{html.escape(title)}\n<a href="{html.escape(link, quote=True)}">보기</a>'
    try:
        response = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}, timeout=(3, 8))
        if response.status_code == 200 and response.json().get("ok"):
            return True
        logging.error("텔레그램 전송 실패: HTTP %s", response.status_code)
    except Exception as exc:
        # 예외 문자열에는 토큰 URL이 포함될 수 있어 종류만 기록합니다.
        logging.error("텔레그램 통신 실패: %s", type(exc).__name__)
    return False

def news_worker():
    while True:
        wake.clear()
        started = time.monotonic()
        config = cfg.snapshot()
        errors = 0
        try:
            if not active_hour(datetime.now(KST).hour, config):
                set_status("수집 시간 외")
            else:
                set_status("수집 중")
                checked = set()
                for kw in config["keywords"]:
                    try:
                        items = engine.fetch_naver(kw, config)
                    except Exception as exc:
                        errors += 1
                        logging.error("검색 실패: %s", str(exc))
                        continue
                    for item in items:
                        info = article_info(item.get("link", ""))
                        if not info or info[2] in checked or db.seen(item):
                            continue
                        checked.add(info[2])
                        title = clean_title(item.get("title", ""))
                        if is_photo(title) or any(ex and ex in title for ex in config["exclude_keywords"]):
                            continue
                        try:
                            media, valid = engine.get_info_and_validate(item, config)
                            if not valid:
                                continue
                            p_date = parsedate_to_datetime(item["pubDate"])
                            if p_date.tzinfo is None:
                                raise ValueError("기사 시간대 없음")
                            db.classify(item, media, p_date.astimezone(KST))
                        except Exception as exc:
                            errors += 1
                            logging.warning("기사 확인 실패 %s: %s", info[2], type(exc).__name__)
                if config.get("telegram_token") and config.get("telegram_chat_id"):
                    for key, title, url in db.pending_alerts():
                        if send_telegram(title, url, config):
                            db.mark_sent(key)
                        else:
                            errors += 1
                            break
                set_status(f"수집 완료 · 오류 {errors}건" if errors else "수집 완료", successful= bool(config["keywords"]))
        except Exception as exc:
            set_status("수집 오류 · 서버 로그 확인")
            logging.error("수집 작업 오류: %s", type(exc).__name__)
        # 처리 시간을 뺀 간격으로 다음 주기를 예약하며, 긴 수집 뒤 최소 1초 휴식.
        wake.wait(max(1, config["check_interval"] - (time.monotonic() - started)))

def start_worker():
    global worker_started
    with worker_lock:
        if not worker_started:
            threading.Thread(target=news_worker, daemon=True, name="news-worker").start()
            worker_started = True

@app.before_request
def ensure_worker():
    start_worker()

@app.route("/")
def index():
    public = cfg.snapshot()
    for key in ("naver_client_id", "naver_client_secret", "telegram_token", "telegram_chat_id"):
        public.pop(key, None)
    with state_lock:
        updated, status = LAST_UPDATE_TIME, STATUS
    return render_template("index.html", c=public, updated=updated, status=status, **db.snapshot())

@app.route("/update_settings", methods=["POST"])
def update_settings():
    try:
        interval = int(request.form.get("interval", ""))
    except ValueError:
        abort(400, "수집 간격은 정수로 입력하세요.")
    if not 10 <= interval <= 86400:
        abort(400, "수집 간격은 10~86400초입니다.")
    cfg.change(lambda c: c.update(check_interval=interval))
    wake.set()
    return redirect(url_for("index"))

def target_key(kind):
    if kind not in {"in", "ex"}:
        abort(404)
    return "keywords" if kind == "in" else "exclude_keywords"

@app.route("/delete/<kind>/<int:idx>", methods=["POST"])
def delete_kw(kind, idx):
    target = target_key(kind)
    def change(c):
        if 0 <= idx < len(c[target]):
            c[target].pop(idx)
    cfg.change(change)
    wake.set()
    return redirect(url_for("index"))

@app.route("/add_kw/<kind>", methods=["POST"])
def add_kw(kind):
    target = target_key(kind)
    kw = request.form.get("new_kw", "").strip()
    def change(c):
        if kw and kw not in c[target]:
            c[target].append(kw)
    cfg.change(change)
    wake.set()
    return redirect(url_for("index"))

@app.route("/search_member")
def search():
    try:
        return jsonify(results=db.search_sheet_data(request.args.get("name", "").strip()))
    except Exception as exc:
        logging.error("의원 검색 실패: %s", type(exc).__name__)
        return jsonify(results=[], error="의원 정보를 불러오지 못했습니다."), 502

@app.route("/reset_logs", methods=["POST"])
def web_reset_logs():
    db.clear_all()
    wake.set()
    return redirect(url_for("index"))

if __name__ == "__main__":
    start_worker()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)), use_reloader=False)
