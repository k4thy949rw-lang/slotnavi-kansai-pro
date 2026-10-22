
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from html.parser import HTMLParser
from urllib.request import Request, urlopen

SOURCE = (
    "https://www.p-world.co.jp/hall/interviews/"
    "prefs/osaka?city_cd=27007"
)
OUTPUT = Path("data/mihara_event_candidates.json")

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

def normalize(value):
    return unicodedata.normalize("NFKC", value)

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
    return normalize(" ".join(parser.parts))

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

        # 店舗名と掲載内容をセットで確認
        blocks = re.split(
            r"(?=HYPER\s*ARROW\s*美原店)",
            section,
            flags=re.IGNORECASE
        )

        for block in blocks[1:]:
            # 他店舗の情報が混ざるのを防ぐ
            block = block[:1500]

            # 店舗所在地が一致する場合のみ採用
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

                if len(name) > 100:
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

def main():
    text = fetch()
    events = collect(text)

    print("日付見出し数:", len(re.findall(
        r"20\d{2}/\d{1,2}/\d{1,2}",
        text
    )))
    print("イベント候補数:", len(events))

    if not events:
        print("抽出0件。既存データは変更しません")
        raise SystemExit(1)

    OUTPUT.parent.mkdir(
        parents=True, exist_ok=True
    )
    OUTPUT.write_text(
        json.dumps(
            events,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    for event in events:
        print(
            event["date"],
            event["type"],
            event["name"]
        )

if __name__ == "__main__":
    main()
