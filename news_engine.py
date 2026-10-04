import requests
from bs4 import BeautifulSoup
from news_utils import article_info, MEDIA

class NewsEngine:
    def __init__(self, config=None):
        self.config = config or {}
        self.session = requests.Session()

    def fetch_naver(self, query, config=None):
        config = config or self.config
        if not config.get("naver_client_id") or not config.get("naver_client_secret"):
            raise RuntimeError("네이버 API 인증정보를 설정하세요.")
        response = self.session.get("https://openapi.naver.com/v1/search/news.json", headers={"X-Naver-Client-Id": config["naver_client_id"], "X-Naver-Client-Secret": config["naver_client_secret"]}, params={"query": query, "display": 100, "sort": "date"}, timeout=(3, 8))
        if response.status_code != 200:
            raise RuntimeError(f"네이버 검색 HTTP {response.status_code}")
        return [item for item in response.json().get("items", []) if article_info(item.get("link", ""))]

    def get_info_and_validate(self, item, config=None):
        config = config or self.config
        info = article_info(item.get("link", ""))
        if not info:
            return None, False
        response = self.session.get(info[3], headers={"User-Agent": "Mozilla/5.0"}, timeout=(3, 5))
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        content = soup.select_one("#newsct_article") or soup.select_one("#articleBodyContents")
        if content is None:
            raise ValueError("기사 본문을 찾지 못했습니다. 다음 주기에 재확인합니다.")
        for node in content.select("script, style"):
            node.decompose()
        # 기존 사진 필터 유지: 짧은 속보도 제외될 수 있으므로 설정으로 조절 가능.
        if len(content.get_text(strip=True)) < config.get("photo_min_chars", 120):
            return None, False
        media = MEDIA.get(info[0])
        if not media:
            logo = soup.select_one(".media_end_head_top_logo img")
            media = logo.get("alt", "뉴스").strip() if logo else "뉴스"
        return media, True
