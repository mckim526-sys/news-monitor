import threading, time, sys, json, requests, os
from flask import Flask, render_template, request, jsonify, redirect, url_for
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from config_manager import ConfigManager
from news_engine import NewsEngine
from data_handler import DataHandler

# 1. 포트 설정 (Render 환경 변수에서 가져오거나 기본값 10000 사용)
PORT = int(os.environ.get("PORT", 10000))

app = Flask(__name__)

# 2. ConfigManager 생성 시 인자(PORT) 제거 (에러 원인 해결)
cfg = ConfigManager() 
engine = NewsEngine(cfg.config)
db = DataHandler()
KST = timezone(timedelta(hours=9))
LAST_UPDATE_TIME = "--:--:--"

def send_telegram(title, link, config):
    token, chat_id = config.get('telegram_token'), config.get('telegram_chat_id')
    if token and chat_id:
        try:
            text = f"🚨 <b>[단독]</b>\n{title}\n<a href='{link}'>보기</a>"
            requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                          data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}, timeout=5)
        except: pass

def news_worker():
    global LAST_UPDATE_TIME
    photo_kws = ["[포토]", "[사진]", "[그래픽]", "포토뉴스"]
    while True:
        try:
            now = datetime.now(KST)
            LAST_UPDATE_TIME = now.strftime("%H:%M:%S")
            for kw in cfg.config.get('keywords', []):
                items = engine.fetch_naver(kw)
                for item in items:
                    title = item.get('title', '').replace("<b>","").replace("</b>","")
                    if any(pk in title for pk in photo_kws): continue
                    if any(ex in title for ex in cfg.config.get('exclude_keywords', [])): continue
                    
                    media, is_valid = engine.get_info_and_validate(item)
                    if not is_valid: continue
                    
                    try: p_date = parsedate_to_datetime(item['pubDate']).astimezone(KST)
                    except: p_date = now
                    
                    if db.classify(item, media, p_date):
                        if any(x in title for x in ["[단독]", "단독"]):
                            send_telegram(title, item['link'], cfg.config)
            time.sleep(cfg.config.get('check_interval', 60))
        except: time.sleep(10)

@app.route('/')
def index():
    return render_template('index.html', c=cfg.config, updated=LAST_UPDATE_TIME, **db.logs)

@app.route('/update_settings', methods=['POST'])
def update_settings():
    try:
        val = request.form.get('interval')
        if val and val.strip().isdigit():
            cfg.config['check_interval'] = int(val.strip())
            cfg.save()
    except: pass
    return redirect(url_for('index'))

# 키워드 삭제 (404 에러 해결을 위해 경로를 명확히 정의)
@app.route('/delete/<type>/<int:idx>')
def delete_kw(type, idx):
    target = 'keywords' if type == 'in' else 'exclude_keywords'
    if target in cfg.config and 0 <= idx < len(cfg.config[target]):
        cfg.config[target].pop(idx)
        cfg.save()
    return redirect(url_for('index'))

@app.route('/add_kw/<type>', methods=['POST'])
def add_kw(type):
    kw = request.form.get('new_kw', '').strip()
    if kw:
        target = 'keywords' if type == 'in' else 'exclude_keywords'
        if kw not in cfg.config.get(target, []):
            cfg.config.setdefault(target, []).append(kw); cfg.save()
    return redirect(url_for('index'))

@app.route('/search_member')
def search():
    name = request.args.get('name', '')
    return jsonify({"results": db.search_sheet_data(name)})

@app.route('/reset_logs')
def web_reset_logs(): # 함수명이 중복되지 않도록 변경
    db.clear_all()
    print("🧹 모든 로그가 초기화되었습니다.")
    return redirect(url_for('index'))

if __name__ == '__main__':
    threading.Thread(target=news_worker, daemon=True).start()
    # 3. app.run 시 정의된 PORT 변수 사용
    app.run(host='0.0.0.0', port=PORT)
