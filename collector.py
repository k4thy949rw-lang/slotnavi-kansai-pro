
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
REQUEST_TIMEOUT = 40
MAX_RETRIES = 3


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
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(
                f"通信開始 ({attempt}/{MAX_RETRIES}): {url}",
                flush=True
            )

            request = Request(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 "
                        "(compatible; SlotNaviKansaiPRO/1.0)"
                    ),
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "ja,en;q=0.8"
                }
            )

            with urlopen(
                request,
                timeout=REQUEST_TIMEOUT
            ) as response:
                content = response.read()

            html = content.decode(
                "utf-8-sig",
                errors="replace"
            )

            print(
                f"通信成功: {url}",
                flush=True
            )

            return html

        except HTTPError as e:
            last_error = e
            print(
                f"HTTPエラー: {e.code} / {url}",
                flush=True
            )

            # 403や404などは無理に再試行しない
            if e.code not in (408, 429, 500, 502, 503, 504):
                break

        except (
            URLError,
            TimeoutError,
            OSError
        ) as e:
            last_error = e
            print(
                f"通信エラー ({attempt}/{MAX_RETRIES}): {e}",
                flush=True
            )

        if attempt < MAX_RETRIES:
            wait = attempt * 3
            print(
                f"{wait}秒待って再試行します",
                flush=True
            )
            time.sleep(wait)

    raise RuntimeError(
        f"ページ取得失敗: {url} / {last_error}"
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
            print(f"記事一覧確認: {url}", flush=True)

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

        except (
            HTTPError,
            URLError,
            TimeoutError,
            OSError,
            RuntimeError
        ) as e:
            print(
                f"記事一覧取得失敗: {url} / {e}",
                flush=True
            )

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


def save_json_safely(path, data):
    """
    一時ファイルに保存してから置き換える。
    保存途中の失敗で既存データを壊さない。
    """
    temporary = path.with_suffix(".tmp")

    try:
        temporary.write_text(
            json.dumps(
                data,
                ensure_ascii=False,
                indent=2
            ),
            encoding="utf-8"
        )

        temporary.replace(path)

    finally:
        if temporary.exists():
            temporary.unlink()


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

    try:
        articles = discover_articles()
    except Exception as e:
        print(
            f"記事一覧の処理でエラー: {e}",
            flush=True
        )
        articles = {}
        status["errors"].append(
            f"記事一覧: {e}"
        )

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

        # 今日と昨日は再取得する
        if (
            output.exists()
            and day < today - timedelta(days=1)
        ):
            status["skipped_dates"].append(date)
            continue

        try:
            print(
                f"台データ取得: {date}",
                flush=True
            )

            html = fetch(articles[date])
            units = parse_units(html, date)

            if not units:
                raise ValueError(
                    "台データを抽出できません"
                )

            save_json_safely(output, units)

            status["saved_dates"].append({
                "date": date,
                "records": len(units),
                "url": articles[date]
            })

            print(
                f"保存成功: {date} / {len(units)}台",
                flush=True
            )

        except (
            HTTPError,
            URLError,
            TimeoutError,
            OSError,
            RuntimeError,
            ValueError
        ) as e:
            message = f"{date}: {e}"
            status["errors"].append(message)

            print(
                f"取得失敗: {message}",
                flush=True
            )

        time.sleep(REQUEST_INTERVAL)

    if status["saved_dates"]:
        status["status"] = "success"

    elif status["skipped_dates"]:
        status["status"] = "partial"

    elif status["errors"]:
        status["status"] = "error"

    save_json_safely(
        DATA_DIR / "status.json",
        status
    )

    print(
        json.dumps(
            status,
            ensure_ascii=False,
            indent=2
        ),
        flush=True
    )

    print(
        "台データ収集処理終了",
        flush=True
    )


if __name__ == "__main__":
    main()
