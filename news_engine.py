import requests
import re
from bs4 import BeautifulSoup

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
            "X-Naver-Client-Id": self.config['naver_client_id'],
            "X-Naver-Client-Secret": self.config['naver_client_secret']
        }
        params = {"query": query, "display": 100, "sort": "date"}
        try:
            res = requests.get(url, headers=headers, params=params, timeout=5)
            if res.status_code == 200:
                return [i for i in res.json().get('items', []) if "news.naver.com" in i['link']]
            return []
        except: return []

    def get_info_and_validate(self, item):
        """매체명 추출 및 사진 기사 여부(본문 길이) 검증"""
        url = item.get('link', '')
        try:
            res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=0.5)
            soup = BeautifulSoup(res.text, 'html.parser')
            
            # 1. 본문 길이 검증 (사진 기사 제외)
            content = soup.select_one('#newsct_article') or soup.select_one('#articleBodyContents')
            if content:
                if len(content.get_text(strip=True)) < 120: # 120자 미만은 제외
                    return None, False
            
            # 2. 매체명 추출
            meta = soup.select_one('meta[property="og:article:author"]') or soup.select_one('meta[name="twitter:creator"]')
            if meta:
                media = re.sub(r'\[.*?\]|\(.*?\)', '', meta['content'].split('|')[0]).strip()
                return media[:10], True
        except: pass
        
        # 크롤링 실패 시 번호 매핑 사용
        oid = re.search(r"article/(\d+)/", url).group(1) if re.search(r"article/(\d+)/", url) else ""
        return self.mapping.get(oid, "뉴스"), True