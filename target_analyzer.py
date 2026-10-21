
import json
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA_DIR = Path("data/arrow_mihara")
OUTPUT = Path("data/arrow_mihara_targets.json")

JST = timezone(timedelta(hours=9))
TODAY = datetime.now(JST).date()
LOOKBACK_DAYS = 90

MIN_GAMES = 3000
MIN_DAYS = 3
MIN_SPECIAL_DAYS = 2


def average(values):
    return round(sum(values) / len(values)) if values else 0


def percentage(count, total):
    return round(count / total * 100, 1) if total else 0


def special_day_names(date):
    names = []
    day = date.day

    if day % 10 == 0:
        names.append("0のつく日")

    if day % 10 == 1:
        names.append("1のつく日")

    if day % 10 == 5:
        names.append("5のつく日")

    if day in (11, 22):
        names.append("ゾロ目の日")

    return names


def summarize(rows):
    if not rows:
        return None

    active = [
        r for r in rows
        if r["games"] >= MIN_GAMES
    ]

    diffs = [r["diff"] for r in rows]

    return {
        "days": len(set(r["date"] for r in rows)),
        "records": len(rows),
        "active_records": len(active),
        "avg_diff": average(diffs),
        "avg_games": average(
            [r["games"] for r in rows]
        ),
        "positive_rate": percentage(
            sum(r["diff"] > 0 for r in rows),
            len(rows)
        ),
        "active_positive_rate": percentage(
            sum(r["diff"] > 0 for r in active),
            len(active)
        )
    }


def score(summary):
    if not summary:
        return 0

    # 0〜100の相対的な注目スコア
    # 設定投入確率ではない
    diff_score = max(
        0, min(100, 50 + summary["avg_diff"] / 40)
    )

    win_score = summary["positive_rate"]

    games_score = min(
        100, summary["avg_games"] / 70
    )

    days_score = min(
        100, summary["days"] / 10 * 100
    )

    return round(
        diff_score * 0.35
        + win_score * 0.30
        + games_score * 0.20
        + days_score * 0.15,
        1
    )


def load_data():
    all_rows = []
    available_dates = set()

    if not DATA_DIR.exists():
        return all_rows, available_dates

    for file in sorted(DATA_DIR.glob("*.json")):
        try:
            date = datetime.strptime(
                file.stem, "%Y-%m-%d"
            ).date()
        except ValueError:
            continue

        age = (TODAY - date).days

        if not 0 <= age < LOOKBACK_DAYS:
            continue

        try:
            data = json.loads(
                file.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            continue

        if not isinstance(data, list):
            continue

        available_dates.add(date.isoformat())

        seen = set()

        for row in data:
            try:
                unit = int(row["unit"])
                machine = str(row["machine"]).strip()
                games = int(row["games"])
                diff = int(row["diff"])
            except (KeyError, ValueError, TypeError):
                continue

            if not machine or games < 0:
                continue

            # 同じ日・同じ台の重複を除外
            if unit in seen:
                continue

            seen.add(unit)

            all_rows.append({
                "date": date.isoformat(),
                "unit": unit,
                "machine": machine,
                "games": games,
                "diff": diff,
                "special_days": special_day_names(date)
            })

    return all_rows, available_dates


def analyze_units(rows):
    groups = defaultdict(list)

    for row in rows:
        groups[(row["unit"], row["machine"])].append(row)

    results = []

    for (unit, machine), items in groups.items():
        summary = summarize(items)

        if summary["days"] < MIN_DAYS:
            continue

        results.append({
            "unit": unit,
            "machine": machine,
            **summary,
            "score": score(summary)
        })

    results.sort(
        key=lambda x: (
            -x["score"],
            -x["days"],
            x["unit"]
        )
    )

    return results


def analyze_special_machines(rows):
    groups = defaultdict(list)
    observed_dates = defaultdict(set)

    for row in rows:
        for name in row["special_days"]:
            key = (name, row["machine"])
            groups[key].append(row)
            observed_dates[name].add(row["date"])

    results = []

    for (name, machine), items in groups.items():
        summary = summarize(items)

        if summary["days"] < MIN_SPECIAL_DAYS:
            continue

        results.append({
            "special_day": name,
            "machine": machine,
            **summary,
            "score": score(summary)
        })

    results.sort(
        key=lambda x: (
            x["special_day"],
            -x["score"],
            -x["days"]
        )
    )

    return results


def analyze_sequences(rows):
    # 同一日・同一機種の連番3台を分析
    daily = defaultdict(dict)

    for row in rows:
        daily[(row["date"], row["machine"])][
            row["unit"]
        ] = row

    groups = defaultdict(list)

    for (date, machine), units in daily.items():
        for start in sorted(units):
            numbers = [start, start + 1, start + 2]

            if not all(n in units for n in numbers):
                continue

            items = [units[n] for n in numbers]

            if not all(
                r["games"] >= MIN_GAMES
                for r in items
            ):
                continue

            avg_diff = average(
                [r["diff"] for r in items]
            )

            positive_count = sum(
                r["diff"] > 0 for r in items
            )

            groups[(machine, start)].append({
                "date": date,
                "avg_diff": avg_diff,
                "positive_count": positive_count,
                "games": average(
                    [r["games"] for r in items]
                )
            })

    results = []

    for (machine, start), items in groups.items():
        if len(items) < MIN_DAYS:
            continue

        strong = [
            r for r in items
            if r["avg_diff"] >= 500
            and r["positive_count"] >= 2
        ]

        strong_rate = percentage(
            len(strong), len(items)
        )

        avg_diff = average(
            [r["avg_diff"] for r in items]
        )

        avg_games = average(
            [r["games"] for r in items]
        )

        # 好成績日の割合を重視
        sequence_score = round(
            strong_rate * 0.55
            + max(
                0,
                min(100, 50 + avg_diff / 40)
            ) * 0.25
            + min(100, len(items) * 10) * 0.20,
            1
        )

        results.append({
            "machine": machine,
            "start_unit": start,
            "end_unit": start + 2,
            "days": len(items),
            "strong_days": len(strong),
            "strong_rate": strong_rate,
            "avg_diff": avg_diff,
            "avg_games": avg_games,
            "score": sequence_score
        })

    results.sort(
        key=lambda x: (
            -x["score"],
            -x["days"],
            x["start_unit"]
        )
    )

    return results


def main():
    rows, dates = load_data()

    if not rows:
        print("分析対象データがありません")
        return

    units = analyze_units(rows)
    special_machines = analyze_special_machines(rows)
    sequences = analyze_sequences(rows)

    result = {
        "updated_at": datetime.now(JST).isoformat(),
        "store": "HYPER ARROW美原店",
        "lookback_days": LOOKBACK_DAYS,
        "total_days": len(dates),
        "total_records": len(rows),
        "conditions": {
            "minimum_games_for_sequence": MIN_GAMES,
            "minimum_unit_days": MIN_DAYS,
            "minimum_special_days": MIN_SPECIAL_DAYS,
            "strong_sequence_avg_diff": 500,
            "strong_sequence_positive_units": 2
        },
        "unit_targets": units,
        "special_machine_targets": special_machines,
        "sequence_targets": sequences,
        "notes": [
            "スコアは独自指標であり設定確率ではありません",
            "特定日は日付から分類しており公式イベントとは限りません",
            "連番3台の好成績は高設定3台並びを意味しません",
            "対象日数が少ない結果は信頼性に注意してください"
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
        f"分析完了: {len(dates)}日、"
        f"台番号{len(units)}件、"
        f"特定日×機種{len(special_machines)}件、"
        f"3台並び{len(sequences)}件"
    )


if __name__ == "__main__":
    main()
