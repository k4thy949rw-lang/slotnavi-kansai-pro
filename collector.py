
import csv
import io
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo
from html.parser import HTMLParser

JST = ZoneInfo("Asia/Tokyo")
STORE = "HYPER ARROW美原店"

# 実際に掲載を確認できた過去データ
SOURCE_URL = (
    "https://slo-navi.com/data/"
    "2026-09-18-11019/"
)

OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)

class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_cell = False
        self.in_row = False
        self.cell = ""
        self.row = []
        self.rows = []

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.in_row = True
            self.row = []
        elif tag in ("td", "th") and self.in_row:
            self.in_cell = True
            self.cell = ""

    def handle_data(self, data):
        if self.in_cell:
            self.cell += data

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.in_cell:
            self.row.append(self.cell.strip())
            self.in_cell = False
        elif tag == "tr" and self.in_row:
            if self.row:
                self.rows.append(self.row)
            self.in_row = False

def number(value):
    value = value.replace(",", "").replace("+", "")
    return int(value)

def fetch_data():
    request = Request(
        SOURCE_URL,
        headers={
            "User-Agent": "SlotNaviKansaiPRO/1.0"
        }
    )
    with urlopen(request, timeout=25) as response:
        return response.read().decode("utf-8")

def parse_data(html):
    parser = TableParser()
    parser.feed(html)

    results = []
    seen = set()

    for row in parser.rows:
        # 機種名、台番号、G数、差枚、BB、RB...
        if len(row) < 6:
            continue

        machine = row[0].strip()

        try:
            unit = number(row[1])
            games = number(row[2])
            diff = number(row[3])
            bb = number(row[4])
            rb = number(row[5])
        except (ValueError, IndexError):
            continue

        if not machine or unit < 1 or games < 0:
            continue

        # 同じ台が複数の集計表に出ても重複保存しない
        if unit in seen:
            continue
        seen.add(unit)

        results.append({
            "store": STORE,
            "date": "2026-09-18",
            "machine": machine,
            "unit": unit,
            "games": games,
            "diff": diff,
            "bb": bb,
            "rb": rb
        })

    return results

def main():
    now = datetime.now(JST)
    status = {
        "checked_at": now.isoformat(),
        "store": STORE,
        "source": SOURCE_URL,
        "status": "error",
        "records": 0
    }

    try:
        html = fetch_data()
        records = parse_data(html)

        if not records:
            raise ValueError(
                "台データを抽出できませんでした。"
                "ページのHTML構造を確認してください。"
            )

        output = OUT_DIR / "arrow_mihara_2026-09-18.json"
        output.write_text(
            json.dumps(records, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        status["status"] = "success"
        status["records"] = len(records)
        print(f"取得成功: {len(records)}台")

    except (HTTPError, URLError, ValueError) as e:
        status["error"] = str(e)
        print(f"取得失敗: {e}")

    (OUT_DIR / "status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(json.dumps(status, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
