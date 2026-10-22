
import json
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from collections import defaultdict

JST = ZoneInfo("Asia/Tokyo")
ROOT = Path("data")
DAILY = ROOT / "arrow_mihara"
EVENT_FILE = ROOT / "mihara_events.json"
OUTPUT = ROOT / "mihara_event_analysis.json"

def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default

def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

def calendar_tags(day):
    n = day.day
    tags = []
    for digit in (0, 1, 5):
        if n % 10 == digit:
            tags.append(f"{digit}のつく日")
    if n in (11, 22):
        tags.append("ゾロ目の日")
    return tags

def load_events():
    events = read_json(EVENT_FILE, [])
    result = defaultdict(list)
    if not isinstance(events, list):
        return result
    for event in events:
        if not isinstance(event, dict):
            continue
        try:
            day = datetime.strptime(
                event["date"], "%Y-%m-%d"
            ).date()
        except (KeyError, TypeError, ValueError):
            continue
        name = str(event.get("name", "")).strip()
        kind = str(event.get("type", "")).strip()
        if not name or not kind:
            continue
        result[day.isoformat()].append({
            "name": name,
            "type": kind,
            "source": event.get("source", ""),
            "status": event.get("status", "unverified")
        })
    return result

def load_daily():
    results = {}
    for path in sorted(DAILY.glob("????-??-??.json")):
        try:
            day = datetime.strptime(
                path.stem, "%Y-%m-%d"
            ).date()
        except ValueError:
            continue

        rows = read_json(path, [])
        if not isinstance(rows, list):
            continue

        seen = set()
        valid = []
        for row in rows:
            try:
                unit = int(row["unit"])
                diff = int(row["diff"])
                games = int(row["games"])
            except (KeyError, ValueError, TypeError):
                continue
            if unit in seen or games < 0:
                continue
            seen.add(unit)
            valid.append({
                "unit": unit,
                "machine": str(row.get("machine", "")),
                "diff": diff,
                "games": games
            })

        if valid:
            results[day.isoformat()] = valid
    return results

def summarize(days, daily):
    rows = [
        row for date in days
        for row in daily.get(date, [])
    ]
    if not rows:
        return {
            "days": 0,
            "records": 0,
            "avg_diff": None,
            "positive_rate": None
        }
    return {
        "days": len([d for d in days if d in daily]),
        "records": len(rows),
        "avg_diff": round(
            sum(r["diff"] for r in rows) / len(rows)
        ),
        "positive_rate": round(
            sum(r["diff"] > 0 for r in rows)
            / len(rows) * 100, 1
        )
    }

def main():
    events = load_events()
    daily = load_daily()
    today = datetime.now(JST).date()
    start = today - timedelta(days=89)

    all_dates = set(daily) | set(events)
    by_tag = defaultdict(set)
    calendar = []

    for date in sorted(all_dates):
        day = datetime.strptime(date, "%Y-%m-%d").date()
        if not start <= day <= today + timedelta(days=90):
            continue

        scheduled = events.get(date, [])
        tags = calendar_tags(day)

        for tag in tags:
            if date in daily:
                by_tag[tag].add(date)

        for event in scheduled:
            if date in daily and event["status"] == "confirmed":
                by_tag["イベント:" + event["name"]].add(date)
                by_tag["種類:" + event["type"]].add(date)

        calendar.append({
            "date": date,
            "calendar_tags": tags,
            "events": scheduled,
            "actual": summarize([date], daily)
                if date in daily else None
        })

    analysis = []
    for tag, dates in by_tag.items():
        result = summarize(sorted(dates), daily)
        analysis.append({"tag": tag, **result})

    analysis.sort(
        key=lambda r: (-r["days"], r["tag"])
    )

    write_json(OUTPUT, {
        "updated_at": datetime.now(JST).isoformat(),
        "store": "HYPER ARROW美原店",
        "calendar": calendar,
        "analysis": analysis,
        "event_count": sum(len(v) for v in events.values())
    })

    print(
        f"イベント分析完了: "
        f"{len(calendar)}日、{len(analysis)}分類"
    )

if __name__ == "__main__":
    main()
