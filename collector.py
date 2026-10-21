
import json
import re
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
DATA_DIR.mkdir(exist_ok=True)


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
            self.links.append((
                self.link_url,
                self.link_text.strip()
            ))
            self.in_link = False

        if tag in ("td", "th") and self.cell is not None:
            self.row.append(self.cell.strip())
            self.cell = None

        if tag == "tr" and self.row is not None:
            if self.row:
                self.rows.append(self.row)
            self.row = None


def fetch(url):
    req = Request(
        url,
        headers={
            "User-Agent": "SlotNaviKansaiPRO/1.0"
        }
    )

    with urlopen(req, timeout=25) as response:
        return response.read().decode(
            "utf-8-sig", errors="replace"
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
            date = match.group(1)
            articles[date] = url

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


def save_units(date, units):
    folder = DATA_DIR / "arrow_mihara"
    folder.mkdir(exist_ok=True)

    path = folder / f"{date}.json"

    path.write_text(
        json.dumps(
            units,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print(f"保存完了: {date} / {len(units)}台")


def main():
    now = datetime.now(JST)

    status = {
        "checked_at": now.isoformat(),
        "store": STORE,
        "status": "no_data",
        "saved_dates": [],
        "errors": []
    }

    try:
        hall_html = fetch(HALL_URL)
        articles = find_articles(hall_html)

        print(f"発見した記事: {len(articles)}件")

        targets = [
            now.date(),
            now.date() - timedelta(days=1)
        ]

        for day in targets:
            date = day.isoformat()

            if date not in articles:
                print(f"未掲載: {date}")
                continue

            try:
                html = fetch(articles[date])
                units = parse_units(html, date)

                if not units:
                    raise ValueError(
                        "台データを抽出できません"
                    )

                save_units(date, units)

                status["saved_dates"].append({
                    "date": date,
                    "records": len(units),
                    "url": articles[date]
                })

            except Exception as e:
                status["errors"].append(
                    f"{date}: {e}"
                )

        if status["saved_dates"]:
            status["status"] = "success"

    except (HTTPError, URLError, ValueError) as e:
        status["status"] = "error"
        status["errors"].append(str(e))

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
