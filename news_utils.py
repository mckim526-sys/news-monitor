import html
import re
from urllib.parse import urlsplit, parse_qs

MEDIA = dict(zip(
    "001 003 421 055 056 214 052 057 437 448 449 422 023 025 020 469 028 032 005 021 081 022".split(),
    "연합뉴스 뉴시스 뉴스1 SBS KBS MBC YTN MBN JTBC TV조선 채널A 연합뉴스TV 조선일보 중앙일보 동아일보 한국일보 한겨레 경향신문 국민일보 문화일보 서울신문 세계일보".split()
))
MEDIA.pop("038", None)
MEDIA.pop("420", None)
AGENCIES = {"001", "003", "421"}
PAPERS = {"023", "020", "025", "032", "028", "469", "005", "021", "081", "022"}
BROADCASTS = {"056", "055", "437", "448", "449", "057", "052", "422"}

def clean_title(value):
    return html.unescape(re.sub(r"</?b>", "", value or "", flags=re.I)).strip()

def article_info(url):
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not (host == "news.naver.com" or host.endswith(".news.naver.com")):
        return None
    match = re.search(r"/article/(\d+)/(\d+)", parsed.path)
    if match:
        oid, aid = match.groups()
    else:
        query = parse_qs(parsed.query)
        oid, aid = query.get("oid", [""])[0], query.get("aid", [""])[0]
    if not (oid.isdigit() and aid.isdigit()):
        return None
    return oid, aid, f"{oid}:{aid}", f"https://n.news.naver.com/mnews/article/{oid}/{aid}"

def is_scoop(title):
    return bool(re.search(r"[\[（(【]\s*단독\s*[\]）)】]", title))

def is_photo(title):
    return bool(re.search(r"[\[（(【]\s*(?:포토(?:뉴스)?|사진|그래픽|포토인뉴스)\s*[\]）)】]|포토뉴스", title, re.I))
