
import json
import re
from datetime import datetime
from pathlib import Path
from html.parser import HTMLParser
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")

SOURCE = (
    "https://www.p-world.co.jp/hall/interviews/"
    "prefs/osaka?city_cd=27007"
)

OUTPUT = Path("data/mihara_event_candidates.json")

class TextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.hidden:
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden:
            value = " ".join(data.split())
            if value:
                self.parts.append(value)

def fetch_text():
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

    parser = TextParser()
    parser.feed(html)
    return " ".join(parser.parts)

def collect(text):
    events = []
    seen = set()

    date_pattern = re.compile(
        r"(20\d{2})/(\d{1,2})/(\d{1,2})"
        r"\s*[\(（][月火水木金土日][\)）]"
        r"\s*の取材・来店情報"
    )

    matches = list(date_pattern.finditer(text))

    for i, match in enumerate(matches):
        year, month, day = map(int, match.groups())

        try:
            date = datetime(year, month, day).date()
        except ValueError:
            continue

        end = (
            matches[i + 1].start()
            if i + 1 < len(matches)
            else len(text)
        )

        section = text[match.end():end]

        hall = re.search(
            r"HYPER\s*ARROW\s*美原店",
            section,
            re.IGNORECASE
        )
        if not hall:
            continue

        section = section[hall.end():]

        # 同じ日付に別店舗がある場合の誤取得を抑制
        next_hall = re.search(
            r"大阪府.{0,30}(?:周辺|パチ)",
            section
        )
        if next_hall:
            section = section[:next_hall.start()]

        pattern = re.compile(
            r"(来店|取材)\s+(.{2,100}?)"
            r"\s+PR\s+\d{1,2}/\d{1,2}"
        )

        for found in pattern.finditer(section):
            kind = found.group(1)
            name = " ".join(found.group(2).split())

            if not name or len(name) > 80:
                continue

            key = (date.isoformat(), kind, name)
            if key in seen:
                continue

            seen.add(key)
            events.append({
                "date": date.isoformat(),
                "name": name,
                "type": kind,
                "source": SOURCE,
                "status": "unverified"
            })

    return events

def main():
    OUTPUT.parent.mkdir(
        parents=True, exist_ok=True
    )

    try:
        text = fetch_text()
        events = collect(text)
    except Exception as error:
        print("イベント取得失敗:", error)
        raise SystemExit(1)

    if not events:
        print("イベント候補を抽出できませんでした")
        print("既存ファイルは変更しません")
        raise SystemExit(1)

    OUTPUT.write_text(
        json.dumps(
            events,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print(f"美原イベント候補: {len(events)}件")
    for event in events:
        print(
            event["date"],
            event["type"],
            event["name"]
        )

if __name__ == "__main__":
    main()
