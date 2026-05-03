import pandas as pd
import requests
import re
from io import BytesIO
from datetime import datetime

class DataHandler:
    def __init__(self):
        # [수정] main.py와 index.html의 변수명에 맞춰 키(Key) 이름을 통일했습니다.
        self.logs = {
            "scoops": [],    # scoop -> scoops
            "mbc": [], 
            "agencies": [],  # agency -> agencies
            "papers": [],    # paper -> papers
            "broadcasts": [], # broadcast -> broadcasts
            "logs": []       # recent -> logs
        }
        self.history = set()
        self.EXPORT_URL = "https://docs.google.com/spreadsheets/d/1Mi5gxnKG0Z6l-beesiVdrR2tey7qfIL6LqyNF1slHww/gviz/tq?tqx=out:csv&gid=1727539678"

    def search_sheet_data(self, query):
        if not query: return []
        try:
            res = requests.get(self.EXPORT_URL, timeout=5)
            df = pd.read_csv(BytesIO(res.content))
            mask = df.apply(lambda row: row.astype(str).str.contains(query, case=False).any(), axis=1)
            results = []
            for _, row in df[mask].iterrows():
                results.append({
                    "name": str(row.get('성명', '미상')),
                    "party": str(row.get('정당', '미상')),
                    "dist": str(row.get('선거구', '미상')),
                    "tel": str(row.get('연락처', '미상'))
                })
            return results
        except: return []

def classify(self, item, media, p_date):
        link = item.get('link', '')
        if link in self.history: return False
        
        title = item.get('title', '').replace("<b>","").replace("</b>","").replace("&quot;", '"')
        oid_match = re.search(r"article/(\d+)/", link)
        oid = oid_match.group(1) if oid_match else ""
        
        news_obj = {
            "media": media.replace("언론사", "").strip()[:8], 
            "title": title, 
            "url": link, 
            "dt": p_date, # 정렬을 위한 datetime 객체
            "display_time": p_date.strftime("%H:%M")
        }

        # 1. 단독 분류 (중복 허용 시 별도 처리)
        if any(x in title for x in ["[단독]", "단독"]):
            self.logs["scoops"].append(news_obj)
            self.logs["scoops"].sort(key=lambda x: x['dt'], reverse=True)
            self.logs["scoops"] = self.logs["scoops"][:100]

        # 2. 매체별 분류
        target_key = "logs"
        if oid == "214": target_key = "mbc"
        elif oid in ["001", "003", "421"]: target_key = "agencies"
        elif oid in ["023", "020", "025", "032", "028", "469", "005", "021", "081", "022", "038", "015", "011"]: target_key = "papers"
        elif oid in ["056", "055", "437", "448", "449", "057", "052", "422", "215", "420"]: target_key = "broadcasts"

        # [수정 포인트] 리스트 끝에 추가 후 'dt' 기준 내림차순 정렬
        self.logs[target_key].append(news_obj)
        self.logs[target_key].sort(key=lambda x: x['dt'], reverse=True)
        self.logs[target_key] = self.logs[target_key][:100]
        
        self.history.add(link)
        return True

    def clear_all(self):
        for k in self.logs: self.logs[k].clear()
        self.history.clear()
