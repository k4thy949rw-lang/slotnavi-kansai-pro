
import csv
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from urllib.request import Request, urlopen

JST = ZoneInfo("Asia/Tokyo")
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

# 取得先は後から追加する
# 取得許可のある公開CSV・JSONのURLを設定
SOURCES = [
    # {
    #     "name": "店舗名",
    #     "url": "https://example.com/data.json",
    #     "format": "json"
    # }
]

def collect(source):
    request = Request(
        source["url"],
        headers={"User-Agent": "SlotNaviKansaiPRO/1.0"}
    )

    with urlopen(request, timeout=20) as response:
        raw = response.read()

    if source["format"] == "json":
        return json.loads(raw.decode("utf-8"))

    if source["format"] == "csv":
        text = raw.decode("utf-8-sig")
        return list(csv.DictReader(text.splitlines()))

    raise ValueError("未対応のデータ形式")

def main():
    now = datetime.now(JST)
    results = []

    for source in SOURCES:
        try:
            data = collect(source)
            results.append({
                "store": source["name"],
                "collected_at": now.isoformat(),
                "data": data
            })
            print(f"取得成功: {source['name']}")
        except Exception as e:
            print(f"取得失敗: {source['name']}: {e}")

    output = DATA_DIR / f"{now:%Y-%m-%d}.json"

    if results:
        existing = []
        if output.exists():
            existing = json.loads(
                output.read_text(encoding="utf-8")
            )
        existing.extend(results)
        output.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    status = {
        "updated_at": now.isoformat(),
        "sources_configured": len(SOURCES),
        "sources_succeeded": len(results),
        "status": "ok" if results else "no_data"
    }

    (DATA_DIR / "status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print("収集処理完了:", status)

if __name__ == "__main__":
    main()
