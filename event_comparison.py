
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path("data")
INPUT = ROOT / "mihara_event_analysis.json"
OUTPUT = ROOT / "mihara_event_comparison.json"

MIN_DAYS = 3
MIN_MACHINE_DAYS = 3


def load_json(path):
    try:
        return json.loads(
            path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return {}


def summarize(days):
    valid = [
        day["actual"]
        for day in days
        if isinstance(day.get("actual"), dict)
        and day["actual"].get("units", 0) > 0
    ]

    units = sum(d["units"] for d in valid)

    if not units:
        return None

    return {
        "days": len(valid),
        "units": units,
        "avg_diff": round(
            sum(d["total_diff"] for d in valid)
            / units
        ),
        "positive_rate": round(
            sum(d["positive_units"] for d in valid)
            / units * 100, 1
        ),
        "avg_games": round(
            sum(
                d["avg_games"] * d["units"]
                for d in valid
            ) / units
        )
    }


def compare(a, b):
    if not a or not b:
        return None

    return {
        "avg_diff_gap": (
            a["avg_diff"] - b["avg_diff"]
        ),
        "positive_rate_gap": round(
            a["positive_rate"]
            - b["positive_rate"], 1
        ),
        "games_gap": (
            a["avg_games"] - b["avg_games"]
        )
    }


def machine_summary(days):
    groups = defaultdict(list)

    for day in days:
        for m in day.get("machines", []):
            if m.get("units", 0) <= 0:
                continue

            groups[m["machine"]].append(m)

    result = {}

    for name, rows in groups.items():
        units = sum(r["units"] for r in rows)

        if not units:
            continue

        result[name] = {
            "days": len(rows),
            "units": units,
            "avg_diff": round(
                sum(r["total_diff"] for r in rows)
                / units
            ),
            "positive_rate": round(
                sum(r["positive_units"] for r in rows)
                / units * 100, 1
            )
        }

    return result


def event_is_confirmed(day):
    return any(
        event.get("status") == "confirmed"
        for event in day.get("events", [])
    )


def main():
    source = load_json(INPUT)

    if not isinstance(source, dict):
        raise SystemExit("分析データを読めません")

    calendar = source.get("calendar", [])

    if not isinstance(calendar, list):
        raise SystemExit("カレンダー形式が不正です")

    today = datetime.now(
        ZoneInfo("Asia/Tokyo")
    ).date().isoformat()

    valid = [
        day for day in calendar
        if isinstance(day, dict)
        and day.get("date", "") < today
        and isinstance(day.get("actual"), dict)
        and day["actual"].get("units", 0) > 0
    ]

    confirmed = [
        d for d in valid
        if event_is_confirmed(d)
    ]

    # 未確認イベントが登録された日は
    # 通常日の比較対象から除外する
    normal = [
        d for d in valid
        if not d.get("events")
    ]

    groups = defaultdict(set)

    for day in confirmed:
        for event in day.get("events", []):
            if event.get("status") != "confirmed":
                continue

            name = str(event.get("name", "")).strip()

            if name:
                groups[name].add(day["date"])

    results = []

    for name, dates in sorted(groups.items()):
        event_days = [
            d for d in confirmed
            if d["date"] in dates
        ]

        weekdays = {
            d["weekday"] for d in event_days
        }

        baseline_days = [
            d for d in normal
            if d.get("weekday") in weekdays
        ]

        event_stats = summarize(event_days)
        baseline_stats = summarize(baseline_days)

        enough = (
            len(event_days) >= MIN_DAYS
            and len(baseline_days) >= MIN_DAYS
        )

        event_machines = machine_summary(event_days)
        baseline_machines = machine_summary(
            baseline_days
        )

        machine_results = []

        if enough:
            for machine, a in event_machines.items():
                b = baseline_machines.get(machine)

                if not b:
                    continue

                if (
                    a["days"] < MIN_MACHINE_DAYS
                    or b["days"] < MIN_MACHINE_DAYS
                ):
                    continue

                machine_results.append({
                    "machine": machine,
                    "event": a,
                    "baseline": b,
                    "avg_diff_gap": (
                        a["avg_diff"] - b["avg_diff"]
                    ),
                    "positive_rate_gap": round(
                        a["positive_rate"]
                        - b["positive_rate"], 1
                    )
                })

        machine_results.sort(
            key=lambda x: x["avg_diff_gap"],
            reverse=True
        )

        results.append({
            "event": name,
            "status": (
                "comparison_available"
                if enough
                else "insufficient_data"
            ),
            "event_days": len(event_days),
            "normal_days": len(baseline_days),
            "event_stats": event_stats,
            "normal_stats": baseline_stats,
            "comparison": (
                compare(event_stats, baseline_stats)
                if enough else None
            ),
            "machine_comparison": machine_results
        })

    output = {
        "updated_at": datetime.now(
            ZoneInfo("Asia/Tokyo")
        ).isoformat(),
        "store": "HYPER ARROW美原店",
        "method": "confirmed_events_vs_same_weekday_no_event_days",
        "minimum_event_days": MIN_DAYS,
        "minimum_normal_days": MIN_DAYS,
        "historical_days_with_data": len(valid),
        "confirmed_event_days": len(confirmed),
        "normal_days": len(normal),
        "comparison_count": sum(
            r["status"] == "comparison_available"
            for r in results
        ),
        "results": results,
        "notes": [
            "未確認イベントは分析対象外",
            "イベント登録日を通常日から除外",
            "同じ曜日の通常日と比較",
            "平均差枚は台数加重平均",
            "同曜日の構成比は完全には一致しない",
            "機種別比較は双方3日以上必要",
            "観測差はイベントの因果効果を示さない",
            "設定投入や将来の勝率を保証しない"
        ]
    }

    OUTPUT.parent.mkdir(
        parents=True, exist_ok=True
    )

    OUTPUT.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print("イベント比較分析完了")
    print("実績取得日:", len(valid))
    print("確認済みイベント日:", len(confirmed))
    print("通常日:", len(normal))
    print("比較可能イベント:", output["comparison_count"])
    print("出力先:", OUTPUT)


if __name__ == "__main__":
    main()
