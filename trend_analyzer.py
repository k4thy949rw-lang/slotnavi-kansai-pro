
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
DATA_DIR = Path("data/arrow_mihara")
OUTPUT = Path("data/arrow_mihara_trends.json")

WEEKDAYS = [
    "月曜日", "火曜日", "水曜日", "木曜日",
    "金曜日", "土曜日", "日曜日"
]

LOOKBACK_DAYS = 90


def load_data():
    today = datetime.now(JST).date()
    records = []

    if not DATA_DIR.exists():
        return records

    for path in sorted(DATA_DIR.glob("????-??-??.json")):
        try:
            day = datetime.strptime(
                path.stem, "%Y-%m-%d"
            ).date()

            age = (today - day).days

            if age < 0 or age > LOOKBACK_DAYS:
                continue

            data = json.loads(
                path.read_text(encoding="utf-8")
            )

            if not isinstance(data, list):
                continue

            seen = set()

            for row in data:
                unit = int(row["unit"])
                games = int(row["games"])
                diff = int(row["diff"])
                machine = str(row["machine"])

                if unit in seen or games < 0:
                    continue

                seen.add(unit)

                records.append({
                    "date": day.isoformat(),
                    "weekday": day.weekday(),
                    "day": day.day,
                    "unit": unit,
                    "machine": machine,
                    "games": games,
                    "diff": diff
                })

        except (
            ValueError, KeyError, TypeError,
            json.JSONDecodeError
        ) as e:
            print(f"読み込みエラー: {path}: {e}")

    return records


def summarize(rows):
    dates = {r["date"] for r in rows}
    total = len(rows)

    if total == 0:
        return {
            "days": 0,
            "records": 0,
            "avg_diff": 0,
            "avg_games": 0,
            "positive_rate": 0
        }

    return {
        "days": len(dates),
        "records": total,
        "avg_diff": round(
            sum(r["diff"] for r in rows) / total
        ),
        "avg_games": round(
            sum(r["games"] for r in rows) / total
        ),
        "positive_rate": round(
            sum(r["diff"] > 0 for r in rows)
            / total * 100, 1
        )
    }


def group_summary(records, key_function):
    groups = defaultdict(list)

    for row in records:
        groups[key_function(row)].append(row)

    return groups


def main():
    records = load_data()

    weekday_groups = group_summary(
        records, lambda r: r["weekday"]
    )

    weekdays = []

    for i, name in enumerate(WEEKDAYS):
        summary = summarize(weekday_groups.get(i, []))

        weekdays.append({
            "weekday": name,
            **summary
        })

    special_groups = {
        "0のつく日": [],
        "1のつく日": [],
        "5のつく日": [],
        "ゾロ目の日": []
    }

    for row in records:
        day = row["day"]

        if day % 10 == 0:
            special_groups["0のつく日"].append(row)

        if day % 10 == 1:
            special_groups["1のつく日"].append(row)

        if day % 10 == 5:
            special_groups["5のつく日"].append(row)

        if day in (11, 22):
            special_groups["ゾロ目の日"].append(row)

    special_days = [
        {"name": name, **summarize(rows)}
        for name, rows in special_groups.items()
    ]

    machine_groups = group_summary(
        records, lambda r: r["machine"]
    )

    machines = [
        {"machine": name, **summarize(rows)}
        for name, rows in machine_groups.items()
    ]

    machines.sort(
        key=lambda r: r["avg_diff"],
        reverse=True
    )

    unit_groups = group_summary(
        records, lambda r: (r["unit"], r["machine"])
    )

    units = [
        {
            "unit": unit,
            "machine": machine,
            **summarize(rows)
        }
        for (unit, machine), rows in unit_groups.items()
    ]

    units.sort(
        key=lambda r: r["avg_diff"],
        reverse=True
    )

    result = {
        "updated_at": datetime.now(JST).isoformat(),
        "store": "HYPER ARROW美原店",
        "lookback_days": LOOKBACK_DAYS,
        "total_records": len(records),
        "total_days": len({
            r["date"] for r in records
        }),
        "weekdays": weekdays,
        "special_days": special_days,
        "machines": machines,
        "units": units
    }

    OUTPUT.parent.mkdir(exist_ok=True)

    OUTPUT.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print("曜日・特定日分析完了")
    print(f"分析日数: {result['total_days']}日")
    print(f"分析レコード: {len(records)}件")

    for row in weekdays:
        print(
            f"{row['weekday']}: "
            f"平均差枚 {row['avg_diff']:+}枚 "
            f"集計{row['days']}日"
        )

    for row in special_days:
        print(
            f"{row['name']}: "
            f"平均差枚 {row['avg_diff']:+}枚 "
            f"集計{row['days']}日"
        )


if __name__ == "__main__":
    main()
