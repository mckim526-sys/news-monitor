import pandas as pd
import requests
import re
from io import BytesIO

class DataHandler:
    def __init__(self):
        self.logs = {"recent":[], "mbc":[], "scoop":[], "agency":[], "paper":[], "broadcast":[]}
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
                    "dist": str(row.get('선거구', '미상')), # 지역구 -> 선거구
                    "tel": str(row.get('연락처', '미상'))   # 전화번호 -> 연락처
                })
            return results
        except: return []

    def classify(self, item, media, p_date):
        link = item.get('link', '')
        if link in self.history: return False
        title = item.get('title', '').replace("<b>","").replace("</b>","").replace("&quot;", '"')
        oid = re.search(r"article/(\d+)/", link).group(1) if re.search(r"article/(\d+)/", link) else ""
        news_obj = {"media": media, "title": title, "url": link, "dt": p_date}

        if any(x in title for x in ["[단독]", "단독"]):
            self.logs["scoop"].insert(0, news_obj)
            self.logs["scoop"] = self.logs["scoop"][:100]

        target_key = "recent"
        if oid == "214": target_key = "mbc"
        elif oid in ["001", "003", "421"]: target_key = "agency"
        elif oid in ["023", "020", "025", "032", "028", "469", "005", "021", "081", "022", "038"]: target_key = "paper"
        elif oid in ["056", "055", "437", "448", "449", "057", "052", "422"]: target_key = "broadcast"

        self.logs[target_key].insert(0, news_obj)
        self.logs[target_key].sort(key=lambda x: x['dt'], reverse=True)
        self.logs[target_key] = self.logs[target_key][:100]
        self.history.add(link)
        return True

    def clear_all(self):
        for k in self.logs: self.logs[k].clear()
        self.history.clear()