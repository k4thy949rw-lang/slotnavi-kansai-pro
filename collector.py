
import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urljoin
from urllib.error import HTTPError, URLError
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
STORE = "HYPER ARROW美原店"
STORE_ID = "11019"

BASE_URL = "https://slo-navi.com"
HALL_URL = f"{BASE_URL}/hall/{STORE_ID}/"

DATA_DIR = Path("data")
STORE_DIR = DATA_DIR / "arrow_mihara"
STORE_DIR.mkdir(parents=True, exist_ok=True)

LOOKBACK_DAYS = 30
MAX_PAGES = 10
REQUEST_INTERVAL = 2


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.rows = []
        self.row = None
        self.cell = None
        self.in_link = False
        self.link_url = ""
        self.link_text = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag == "a":
            self.in_link = True
            self.link_url = attrs.get("href", "")
            self.link_text = ""

        if tag == "tr":
            self.row = []

        if tag in ("td", "th") and self.row is not None:
            self.cell = ""

    def handle_data(self, data):
        if self.in_link:
            self.link_text += data

        if self.cell is not None:
            self.cell += data

    def handle_endtag(self, tag):
        if tag == "a" and self.in_link:
            self.links.append(
                (self.link_url, self.link_text.strip())
            )
            self.in_link = False

        if tag in ("td", "th") and self.cell is not None:
            self.row.append(self.cell.strip())
            self.cell = None

        if tag == "tr" and self.row is not None:
            if self.row:
                self.rows.append(self.row)
            self.row = None


def fetch(url):
    request = Request(
        url,
        headers={
            "User-Agent": "SlotNaviKansaiPRO/1.0"
        }
    )

    with urlopen(request, timeout=25) as response:
        return response.read().decode(
            "utf-8-sig",
            errors="replace"
        )


def to_int(value):
    return int(
        value.replace(",", "")
             .replace("+", "")
             .replace("−", "-")
             .strip()
    )


def find_articles(html):
    parser = PageParser()
    parser.feed(html)

    articles = {}

    pattern = re.compile(
        rf"/data/(\d{{4}}-\d{{2}}-\d{{2}})-{STORE_ID}/"
    )

    for href, title in parser.links:
        url = urljoin(BASE_URL, href)
        match = pattern.search(url)

        if match:
            articles[match.group(1)] = url

    return articles


def discover_articles():
    articles = {}
    visited = set()
    pending = [HALL_URL]

    while pending and len(visited) < MAX_PAGES:
        url = pending.pop(0)

        if url in visited:
            continue

        visited.add(url)

        try:
            print(f"記事一覧確認: {url}")
            html = fetch(url)

            articles.update(find_articles(html))

            parser = PageParser()
            parser.feed(html)

            for href, title in parser.links:
                next_url = urljoin(url, href)

                if not next_url.startswith(HALL_URL):
                    continue

                if next_url in visited or next_url in pending:
                    continue

                if re.search(r"/page/\d+/?$", next_url):
                    pending.append(next_url)

        except (HTTPError, URLError) as e:
            print(f"一覧取得失敗: {e}")

        time.sleep(REQUEST_INTERVAL)

    return articles


def parse_units(html, date):
    parser = PageParser()
    parser.feed(html)

    units = []
    seen = set()

    for row in parser.rows:
        if len(row) < 6:
            continue

        try:
            machine = row[0].strip()
            unit = to_int(row[1])
            games = to_int(row[2])
            diff = to_int(row[3])
            bb = to_int(row[4])
            rb = to_int(row[5])

        except (ValueError, IndexError):
            continue

        if not machine or unit <= 0 or games < 0:
            continue

        if unit in seen:
            continue

        seen.add(unit)

        units.append({
            "store": STORE,
            "date": date,
            "machine": machine,
            "unit": unit,
            "games": games,
            "diff": diff,
            "bb": bb,
            "rb": rb
        })

    return units


def main():
    now = datetime.now(JST)
    today = now.date()

    status = {
        "checked_at": now.isoformat(),
        "store": STORE,
        "status": "no_data",
        "discovered_articles": 0,
        "saved_dates": [],
        "skipped_dates": [],
        "errors": []
    }

    articles = discover_articles()
    status["discovered_articles"] = len(articles)

    target_dates = [
        today - timedelta(days=i)
        for i in range(LOOKBACK_DAYS + 1)
    ]

    for day in target_dates:
        date = day.isoformat()

        if date not in articles:
            continue

        output = STORE_DIR / f"{date}.json"

        # 今日・昨日は更新の可能性があるので再取得
        if output.exists() and day < today - timedelta(days=1):
            status["skipped_dates"].append(date)
            continue

        try:
            print(f"台データ取得: {date}")

            html = fetch(articles[date])
            units = parse_units(html, date)

            if not units:
                raise ValueError("台データを抽出できません")

            output.write_text(
                json.dumps(
                    units,
                    ensure_ascii=False,
                    indent=2
                ),
                encoding="utf-8"
            )

            status["saved_dates"].append({
                "date": date,
                "records": len(units),
                "url": articles[date]
            })

            print(f"保存成功: {date} / {len(units)}台")

        except (HTTPError, URLError, ValueError) as e:
            status["errors"].append(f"{date}: {e}")
            print(f"取得失敗: {date} / {e}")

        time.sleep(REQUEST_INTERVAL)

    if status["saved_dates"] or status["skipped_dates"]:
        status["status"] = "success"
    elif status["errors"]:
        status["status"] = "error"

    (DATA_DIR / "status.json").write_text(
        json.dumps(
            status,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print(json.dumps(
        status,
        ensure_ascii=False,
        indent=2
    ))


if __name__ == "__main__":
    main()
