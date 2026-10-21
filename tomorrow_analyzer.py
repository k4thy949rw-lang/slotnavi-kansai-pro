
import json
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
TODAY = datetime.now(JST).date()
TARGET_DATE = TODAY + timedelta(days=1)

DATA_DIR = Path("data/arrow_mihara")
OUTPUT = Path("data/arrow_mihara_tomorrow.json")

LOOKBACK_DAYS = 90
MIN_DAYS = 3
MAX_RESULTS = 100

WEEKDAYS = [
    "月曜日", "火曜日", "水曜日", "木曜日",
    "金曜日", "土曜日", "日曜日"
]


def special_days(day):
    names = []
    n = day.day

    if n % 10 == 0:
        names.append("0のつく日")
    if n % 10 == 1:
        names.append("1のつく日")
    if n % 10 == 5:
        names.append("5のつく日")
    if n in (11, 22):
        names.append("ゾロ目の日")

    return names


def average(values):
    return sum(values) / len(values) if values else 0


def percent(values):
    if not values:
        return 0
    return 100 * sum(v > 0 for v in values) / len(values)


def clamp(value):
    return max(0, min(100, value))


def performance_score(rows):
    if not rows:
        return 50.0

    diffs = [r["diff"] for r in rows]
    games = [r["games"] for r in rows]

    diff_part = clamp(50 + average(diffs) / 40)
    win_part = percent(diffs)
    games_part = clamp(average(games) / 70)

    return (
        diff_part * 0.45
        + win_part * 0.35
        + games_part * 0.20
    )


def load_rows():
    rows = []
    dates = set()

    if not DATA_DIR.exists():
        return rows, dates

    for path in sorted(DATA_DIR.glob("*.json")):
        try:
            day = datetime.strptime(
                path.stem, "%Y-%m-%d"
            ).date()
        except ValueError:
            continue

        age = (TODAY - day).days

        if not 0 <= age < LOOKBACK_DAYS:
            continue

        try:
            data = json.loads(
                path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            continue

        if not isinstance(data, list):
            continue

        seen = set()
        valid_count = 0

        for item in data:
            try:
                unit = int(item["unit"])
                machine = str(item["machine"]).strip()
                games = int(item["games"])
                diff = int(item["diff"])
            except (KeyError, ValueError, TypeError):
                continue

            if not machine or games < 0 or unit in seen:
                continue

            seen.add(unit)
            valid_count += 1

            rows.append({
                "date": day.isoformat(),
                "day": day,
                "unit": unit,
                "machine": machine,
                "games": games,
                "diff": diff
            })

        if valid_count:
            dates.add(day.isoformat())

    return rows, dates


def summarize(rows):
    diffs = [r["diff"] for r in rows]
    games = [r["games"] for r in rows]

    return {
        "days": len(set(r["date"] for r in rows)),
        "records": len(rows),
        "avg_diff": round(average(diffs)),
        "avg_games": round(average(games)),
        "positive_rate": round(percent(diffs), 1)
    }


def analyze_group(key, rows, target_special):
    groups = defaultdict(list)

    for row in rows:
        groups[key(row)].append(row)

    results = []

    for group_key, items in groups.items():
        all_days = len(set(r["date"] for r in items))

        if all_days < MIN_DAYS:
            continue

        same_weekday = [
            r for r in items
            if r["day"].weekday()
            == TARGET_DATE.weekday()
        ]

        matching_special = [
            r for r in items
            if target_special
            and any(
                name in special_days(r["day"])
                for name in target_special
            )
        ]

        recent = [
            r for r in items
            if (TODAY - r["day"]).days <= 14
        ]

        overall = performance_score(items)

        # 条件別データが少ない場合は
        # 全体実績に近づけて過信を防ぐ
        def shrink(sample, prior_weight):
            if not sample:
                return overall

            n = len(set(r["date"] for r in sample))

            return (
                performance_score(sample) * n
                + overall * prior_weight
            ) / (n + prior_weight)

        weekday_score = shrink(same_weekday, 5)
        special_score = shrink(matching_special, 5)
        recent_score = shrink(recent, 7)

        if target_special:
            raw_score = (
                overall * 0.25
                + weekday_score * 0.20
                + special_score * 0.40
                + recent_score * 0.15
            )
        else:
            raw_score = (
                overall * 0.40
                + weekday_score * 0.35
                + recent_score * 0.25
            )

        # サンプル数が少ないほど中立値へ補正
        reliability = all_days / (all_days + 5)

        final_score = (
            50 + (raw_score - 50) * reliability
        )

        results.append({
            "key": group_key,
            **summarize(items),
            "weekday_days": len(set(
                r["date"] for r in same_weekday
            )),
            "special_days_count": len(set(
                r["date"] for r in matching_special
            )),
            "recent_days": len(set(
                r["date"] for r in recent
            )),
            "score": round(clamp(final_score), 1)
        })

    results.sort(
        key=lambda r: (
            -r["score"],
            -r["days"],
            str(r["key"])
        )
    )

    return results


def main():
    rows, dates = load_rows()

    if not rows:
        print("分析対象データがありません")
        return

    target_special = special_days(TARGET_DATE)

    machines = analyze_group(
        lambda r: r["machine"],
        rows,
        target_special
    )

    units = analyze_group(
        lambda r: (r["unit"], r["machine"]),
        rows,
        target_special
    )

    machine_results = [
        {
            "machine": r["key"],
            **{k: v for k, v in r.items() if k != "key"}
        }
        for r in machines[:MAX_RESULTS]
    ]

    unit_results = [
        {
            "unit": r["key"][0],
            "machine": r["key"][1],
            **{k: v for k, v in r.items() if k != "key"}
        }
        for r in units[:MAX_RESULTS]
    ]

    result = {
        "updated_at": datetime.now(JST).isoformat(),
        "store": "HYPER ARROW美原店",
        "target_date": TARGET_DATE.isoformat(),
        "target_weekday": WEEKDAYS[
            TARGET_DATE.weekday()
        ],
        "target_special_days": target_special,
        "lookback_days": LOOKBACK_DAYS,
        "total_days": len(dates),
        "total_records": len(rows),
        "machine_predictions": machine_results,
        "unit_predictions": unit_results,
        "notes": [
            "翌日の設定投入を予知するものではありません",
            "スコアは独自の過去実績指標であり確率ではありません",
            "曜日・特定日のサンプルが少ない場合は全体実績に近づけて補正します",
            "特定日はカレンダーによる分類で公式イベントを示しません",
            "当日のデータが未収集の場合は保存済みデータのみで計算します"
        ]
    }

    OUTPUT.parent.mkdir(
        parents=True, exist_ok=True
    )

    OUTPUT.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print(
        f"翌日予測完了: {TARGET_DATE} "
        f"機種{len(machine_results)}件 "
        f"台番号{len(unit_results)}件"
    )


if __name__ == "__main__":
    main()
