import threading, time, sys, json, requests, os, re
from flask import Flask, render_template, request, jsonify, redirect, url_for
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from bs4 import BeautifulSoup

# --- [1. 설정 관리 클래스] ---
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

# --- [2. 뉴스 수집 엔진 클래스] ---
class NewsEngine:
    def __init__(self, config):
        self.config = config
        self.mapping = {
            "001": "연합뉴스", "003": "뉴시스", "421": "뉴스1",
            "055": "SBS", "056": "KBS", "214": "MBC", "052": "YTN", "057": "MBN",
            "437": "JTBC", "448": "TV조선", "449": "채널A", "422": "연합뉴스TV",
            "023": "조선일보", "025": "중앙일보", "020": "동아일보", "469": "한국일보",
            "028": "한겨레", "032": "경향신문", "005": "국민일보", "021": "문화일보"
        }

    def fetch_naver(self, query):
        url = "https://openapi.naver.com/v1/search/news.json"
        headers = {
            "X-Naver-Client-Id": self.config.get('naver_client_id'),
            "X-Naver-Client-Secret": self.config.get('naver_client_secret')
        }
        params = {"query": query, "display": 100, "sort": "date"}
        try:
            res = requests.get(url, headers=headers, params=params, timeout=5)
            if res.status_code == 200:
                return [i for i in res.json().get('items', []) if "news.naver.com" in i['link']]
            return []
        except: return []

    def get_info_and_validate(self, item):
        url = item.get('link', '')
        try:
            res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=1.0)
            soup = BeautifulSoup(res.text, 'html.parser')
            content = soup.select_one('#newsct_article') or soup.select_one('#articleBodyContents')
            if content and len(content.get_text(strip=True)) < 120:
                return None, False
            meta = soup.select_one('meta[property="og:article:author"]') or soup.select_one('meta[name="twitter:creator"]')
            if meta:
                media = re.sub(r'\[.*?\]|\(.*?\)', '', meta['content'].split('|')[0]).strip()
                return media[:10], True
        except: pass
        oid = re.search(r"article/(\d+)/", url).group(1) if re.search(r"article/(\d+)/", url) else ""
        return self.mapping.get(oid, "뉴스"), True

# --- [3. 데이터 핸들러 클래스] ---
class DataHandler:
    def __init__(self):
        self.logs = {"scoops": [], "mbc": [], "agencies": [], "papers": [], "broadcasts": [], "logs": []}
        self.history = set()

    def classify(self, item, media, p_date):
        link = item.get('link', '')
        if link in self.history: return False
        
        title = item.get('title', '').replace("<b>","").replace("</b>","").replace("&quot;", '"')
        oid_match = re.search(r"article/(\d+)/", link)
        oid = oid_match.group(1) if oid_match else ""
        clean_media = media.replace("언론사", "").strip()

        news_obj = {
            "media": clean_media[:8], "title": title, "url": link, 
            "dt": p_date, "display_time": p_date.strftime("%H:%M")
        }

        if any(x in title for x in ["[단독]", "단독"]):
            self.logs["scoops"].insert(0, news_obj)

        target = "logs"
        if oid == "214": target = "mbc"
        elif oid in ["001", "003", "421"]: target = "agencies"
        elif oid in ["023", "020", "025", "032", "028", "469", "005", "021", "081", "022", "038"]: target = "papers"
        elif oid in ["056", "055", "437", "448", "449", "057", "052", "422"]: target = "broadcasts"

        self.logs[target].insert(0, news_obj)
        self.logs[target] = self.logs[target][:100]
        self.history.add(link)
        return True

    def clear_all(self):
        for k in self.logs: self.logs[k].clear()
        self.history.clear()

# --- [4. Flask 웹 서버 설정] ---
app = Flask(__name__)
KST = timezone(timedelta(hours=9))
LAST_UPDATE = "--:--:--"

cfg = ConfigManager()
engine = NewsEngine(cfg.config)
db = DataHandler()

def send_telegram(title, link):
    token, chat_id = cfg.config.get('telegram_token'), cfg.config.get('telegram_chat_id')
    if token and chat_id:
        try:
            text = f"🚨 <b>[단독]</b>\n{title}\n<a href='{link}'>보기</a>"
            requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                          data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}, timeout=5)
        except: pass

def news_worker():
    global LAST_UPDATE
    while True:
        try:
            now = datetime.now(KST)
            LAST_UPDATE = now.strftime("%H:%M:%S")
            for kw in cfg.config.get('keywords', []):
                items = engine.fetch_naver(kw)
                for item in items:
                    media, is_valid = engine.get_info_and_validate(item)
                    if not is_valid: continue
                    try: p_date = parsedate_to_datetime(item['pubDate']).astimezone(KST)
                    except: p_date = now
                    if db.classify(item, media, p_date):
                        if any(x in item.get('title','') for x in ["[단독]", "단독"]):
                            send_telegram(item.get('title','').replace("<b>","").replace("</b>",""), item['link'])
            time.sleep(cfg.config.get('check_interval', 60))
        except: time.sleep(10)

@app.route('/')
def index():
    return render_template('index.html', c=cfg.config, updated=LAST_UPDATE, now=datetime.now(), **db.logs)

@app.route('/add_kw/in', methods=['POST'])
def add_kw():
    kw = request.form.get('new_kw', '').strip()
    if kw and kw not in cfg.config['keywords']:
        cfg.config['keywords'].append(kw); cfg.save()
    return redirect(url_for('index'))

@app.route('/delete/<type>/<int:idx>')
def delete_kw(type, idx):
    target = 'keywords' if type == 'in' else 'exclude_keywords'
    if target in cfg.config and 0 <= idx < len(cfg.config[target]):
        cfg.config[target].pop(idx); cfg.save()
    return redirect(url_for('index'))

# 사용자님의 버튼 링크(/reset_logs)와 일치시킨 함수
@app.route('/reset_logs')
def reset_logs():
    try:
        db.clear_all() # DataHandler 내의 모든 리스트와 히스토리 삭제
        print("🧹 리셋 버튼 클릭: 모든 데이터 초기화 완료")
    except Exception as e:
        print(f"Reset Error: {e}")
    
    return redirect(url_for('index'))

@app.route('/reset')
def reset():
    db.clear_all()
    return redirect(url_for('index'))

if __name__ == '__main__':
    threading.Thread(target=news_worker, daemon=True).start()
    port = int(os.environ.get("PORT", 5001))
    app.run(host='0.0.0.0', port=port)
