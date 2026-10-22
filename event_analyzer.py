
import json
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from collections import defaultdict

JST = ZoneInfo("Asia/Tokyo")
ROOT = Path("data")
DAILY = ROOT / "arrow_mihara"

MANUAL_FILE = ROOT / "mihara_events.json"
AUTO_FILE = ROOT / "mihara_event_candidates.json"
OUTPUT = ROOT / "mihara_event_analysis.json"

TODAY = datetime.now(JST).date()
HISTORY_DAYS = 180
FUTURE_DAYS = 90


def read_json(path, default):
    try:
        return json.loads(
            path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return default


def write_json(path, data):
    path.parent.mkdir(
        parents=True, exist_ok=True
    )
    path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2
        ),
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
    events = {}

    sources = [
        (AUTO_FILE, "automatic"),
        (MANUAL_FILE, "manual")
    ]

    for path, origin in sources:
        data = read_json(path, [])

        if not isinstance(data, list):
            continue

        for item in data:
            if not isinstance(item, dict):
                continue

            try:
                date = datetime.strptime(
                    item["date"], "%Y-%m-%d"
                ).date().isoformat()
            except (KeyError, TypeError, ValueError):
                continue

            name = str(
                item.get("name", "")
            ).strip()

            kind = str(
                item.get("type", "")
            ).strip()

            if not name or not kind:
                continue

            # テスト用イベントは分析対象外
            if name == "イベント登録テスト":
                continue

            key = (
                date,
                name,
                kind
            )

            event = {
                "date": date,
                "name": name,
                "type": kind,
                "source": str(
                    item.get("source", "")
                ),
                "status": (
                    "confirmed"
                    if item.get("status") == "confirmed"
                    else "unverified"
                ),
                "origin": origin
            }

            # 同じイベントが手動登録されている場合は
            # 手動データを優先する
            if key not in events or origin == "manual":
                events[key] = event

    result = defaultdict(list)

    for event in events.values():
        result[event["date"]].append(event)

    return result


def load_daily():
    result = {}

    if not DAILY.exists():
        return result

    for path in sorted(
        DAILY.glob("????-??-??.json")
    ):
        try:
            date = datetime.strptime(
                path.stem, "%Y-%m-%d"
            ).date()
        except ValueError:
            continue

        if not (
            TODAY - timedelta(days=HISTORY_DAYS - 1)
            <= date <= TODAY
        ):
            continue

        data = read_json(path, [])

        if not isinstance(data, list):
            continue

        seen = set()
        rows = []

        for item in data:
            try:
                unit = int(item["unit"])
                games = int(item["games"])
                diff = int(item["diff"])
                machine = str(
                    item["machine"]
                ).strip()
            except (KeyError, ValueError, TypeError):
                continue

            if (
                unit in seen
                or games < 0
                or not machine
            ):
                continue

            seen.add(unit)

            rows.append({
                "unit": unit,
                "machine": machine,
                "games": games,
                "diff": diff
            })

        if rows:
            result[date.isoformat()] = rows

    return result


def summarize(rows):
    if not rows:
        return None

    diffs = [r["diff"] for r in rows]

    return {
        "units": len(rows),
        "total_diff": sum(diffs),
        "avg_diff": round(
            sum(diffs) / len(diffs)
        ),
        "avg_games": round(
            sum(r["games"] for r in rows)
            / len(rows)
        ),
        "positive_units": sum(
            d > 0 for d in diffs
        ),
        "positive_rate": round(
            sum(d > 0 for d in diffs)
            / len(diffs) * 100,
            1
        )
    }


def machine_summary(rows):
    grouped = defaultdict(list)

    for row in rows:
        grouped[row["machine"]].append(row)

    results = []

    for machine, items in grouped.items():
        summary = summarize(items)

        results.append({
            "machine": machine,
            **summary
        })

    results.sort(
        key=lambda x: x["avg_diff"],
        reverse=True
    )

    return results


def main():
    events = load_events()
    daily = load_daily()

    dates = set(events) | set(daily)

    calendar = []
    event_groups = defaultdict(set)
    type_groups = defaultdict(set)
    tag_groups = defaultdict(set)

    history_start = TODAY - timedelta(
        days=HISTORY_DAYS - 1
    )
    future_end = TODAY + timedelta(
        days=FUTURE_DAYS
    )

    for date in sorted(dates):
        day = datetime.strptime(
            date, "%Y-%m-%d"
        ).date()

        if not history_start <= day <= future_end:
            continue

        rows = daily.get(date, [])
        day_events = events.get(date, [])
        tags = calendar_tags(day)

        actual = summarize(rows)
        machines = machine_summary(rows)

        calendar.append({
            "date": date,
            "weekday": day.weekday(),
            "calendar_tags": tags,
            "events": day_events,
            "actual": actual,
            "machines": machines
        })

        if not rows:
            continue

        for tag in tags:
            tag_groups[tag].add(date)

        for event in day_events:
            # 未確認情報は統計に採用しない
            if event["status"] != "confirmed":
                continue

            event_groups[
                event["name"]
            ].add(date)

            type_groups[
                event["type"]
            ].add(date)

    def group_analysis(groups):
        result = []

        for name, group_dates in groups.items():
            all_rows = []

            for date in sorted(group_dates):
                all_rows.extend(
                    daily.get(date, [])
                )

            summary = summarize(all_rows)

            if not summary:
                continue

            result.append({
                "name": name,
                "days": len(group_dates),
                **summary,
                "machines": machine_summary(
                    all_rows
                )
            })

        result.sort(
            key=lambda x: (
                -x["days"],
                -x["avg_diff"]
            )
        )

        return result

    tag_analysis = group_analysis(
        tag_groups
    )

    event_analysis = group_analysis(
        event_groups
    )

    type_analysis = group_analysis(
        type_groups
    )

    all_events = [
        event
        for day_events in events.values()
        for event in day_events
    ]

    upcoming = sorted(
        [
            event
            for event in all_events
            if event["date"] >= TODAY.isoformat()
        ],
        key=lambda x: (
            x["date"],
            x["name"]
        )
    )

    result = {
        "updated_at": datetime.now(
            JST
        ).isoformat(),
        "store": "HYPER ARROW美原店",
        "history_days": HISTORY_DAYS,
        "future_days": FUTURE_DAYS,
        "event_count": len(all_events),
        "confirmed_count": sum(
            e["status"] == "confirmed"
            for e in all_events
        ),
        "unverified_count": sum(
            e["status"] != "confirmed"
            for e in all_events
        ),
        "upcoming_events": upcoming,
        "calendar": calendar,
        "tag_analysis": tag_analysis,
        "event_analysis": event_analysis,
        "type_analysis": type_analysis,
        # 旧画面との互換性を維持
        "analysis": [
            {
                "tag": row["name"],
                "days": row["days"],
                "records": row["units"],
                "avg_diff": row["avg_diff"],
                "positive_rate": row["positive_rate"]
            }
            for row in tag_analysis
        ]
    }

    write_json(OUTPUT, result)

    print("美原イベント分析完了")
    print("イベント総数:", len(all_events))
    print(
        "確認済み:",
        result["confirmed_count"]
    )
    print(
        "未確認:",
        result["unverified_count"]
    )
    print(
        "今後のイベント:",
        len(upcoming)
    )
    print(
        "カレンダー日数:",
        len(calendar)
    )


if __name__ == "__main__":
    main()
