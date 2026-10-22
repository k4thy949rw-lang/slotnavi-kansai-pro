
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from html.parser import HTMLParser
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

SOURCE = (
    "https://www.p-world.co.jp/hall/interviews/"
    "prefs/osaka?city_cd=27007"
)

OUTPUT = Path("data/mihara_event_candidates.json")
JST = ZoneInfo("Asia/Tokyo")


class Parser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            value = " ".join(data.split())
            if value:
                self.parts.append(value)


def fetch():
    request = Request(
        SOURCE,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "ja-JP,ja;q=0.9"
        }
    )

    with urlopen(request, timeout=30) as response:
        html = response.read().decode(
            "utf-8", errors="replace"
        )

    parser = Parser()
    parser.feed(html)

    return unicodedata.normalize(
        "NFKC", " ".join(parser.parts)
    )


def collect(text):
    events = []
    seen = set()

    dates = list(re.finditer(
        r"(20\d{2})/(\d{1,2})/(\d{1,2})"
        r"\s*\([月火水木金土日]\)"
        r"\s*の取材・来店情報",
        text
    ))

    for i, match in enumerate(dates):
        try:
            day = datetime(
                *map(int, match.groups())
            ).date().isoformat()
        except ValueError:
            continue

        end = (
            dates[i + 1].start()
            if i + 1 < len(dates)
            else len(text)
        )

        section = text[match.end():end]

        blocks = re.split(
            r"(?=HYPER\s*ARROW\s*美原店)",
            section,
            flags=re.IGNORECASE
        )

        for block in blocks[1:]:
            block = block[:1500]

            if "堺市美原区黒山1000" not in block:
                continue

            for found in re.finditer(
                r"(来店|取材)\s+(.{2,120}?)"
                r"\s+PR\s+\d{1,2}/\d{1,2}"
                r"\s*\([月火水木金土日]\)",
                block
            ):
                kind = found.group(1)
                name = " ".join(
                    found.group(2).split()
                )

                if not name or len(name) > 100:
                    continue

                key = (day, kind, name)

                if key in seen:
                    continue

                seen.add(key)

                events.append({
                    "date": day,
                    "name": name,
                    "type": kind,
                    "source": SOURCE,
                    "status": "unverified"
                })

    return events


def read_history():
    if not OUTPUT.exists():
        return []

    try:
        data = json.loads(
            OUTPUT.read_text(encoding="utf-8")
        )
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def event_key(event):
    return (
        str(event.get("date", "")),
        str(event.get("type", "")).strip(),
        str(event.get("name", "")).strip()
    )


def valid_event(event):
    if not isinstance(event, dict):
        return False

    date, kind, name = event_key(event)

    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return False

    return bool(kind and name)


def merge_history(old, new, now):
    merged = {}

    # 既存履歴を先に保存
    for event in old:
        if not valid_event(event):
            continue

        key = event_key(event)
        merged[key] = dict(event)

    # 今回取得した情報を照合
    for event in new:
        if not valid_event(event):
            continue

        key = event_key(event)

        if key not in merged:
            merged[key] = {
                **event,
                "first_seen": now,
                "last_collected_at": now,
                "seen_count": 1,
                "source_history": [SOURCE]
            }
            continue

        previous = merged[key]

        previous.setdefault(
            "first_seen", now
        )

        previous["last_collected_at"] = now

        previous["seen_count"] = (
            int(previous.get("seen_count", 1)) + 1
        )

        sources = previous.get(
            "source_history", []
        )

        if not isinstance(sources, list):
            sources = []

        if SOURCE not in sources:
            sources.append(SOURCE)

        previous["source_history"] = sources

        # 確認済み状態を勝手に取り消さない
        if previous.get("status") != "confirmed":
            previous["status"] = "unverified"

    return sorted(
        merged.values(),
        key=lambda x: event_key(x)
    )


def main():
    now = datetime.now(JST).isoformat()
    old = read_history()

    try:
        text = fetch()
        new = collect(text)
    except Exception as error:
        print("取得失敗:", error)
        print("既存履歴は維持します")
        raise SystemExit(1)

    print("今回取得:", len(new), "件")
    print("既存履歴:", len(old), "件")

    if not new:
        print("抽出0件。既存履歴は維持します")
        raise SystemExit(1)

    merged = merge_history(old, new, now)

    OUTPUT.parent.mkdir(
        parents=True, exist_ok=True
    )

    OUTPUT.write_text(
        json.dumps(
            merged,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print("累計保存:", len(merged), "件")
    print("新規追加:", len(merged) - len(old), "件")
    print("最終取得:", now)


if __name__ == "__main__":
    main()
