
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone

DATA_DIR = Path("data/arrow_mihara")
OUTPUT = Path("data/arrow_mihara_history.json")

JST = timezone(timedelta(hours=9))
TODAY = datetime.now(JST).date()
LOOKBACK_DAYS = 30

def main():
    histories = {}
    dates = set()

    if not DATA_DIR.exists():
        print("データフォルダがありません")
        return

    for file in sorted(DATA_DIR.glob("*.json")):
        try:
            date = datetime.strptime(
                file.stem, "%Y-%m-%d"
            ).date()
        except ValueError:
            continue

        if not 0 <= (TODAY - date).days < LOOKBACK_DAYS:
            continue

        try:
            rows = json.loads(
                file.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            continue

        if not isinstance(rows, list):
            continue

        dates.add(date.isoformat())

        for row in rows:
            try:
                unit = int(row["unit"])
                machine = str(row["machine"])
                games = int(row["games"])
                diff = int(row["diff"])
            except (KeyError, TypeError, ValueError):
                continue

            key = f"{unit}|{machine}"

            if key not in histories:
                histories[key] = {
                    "unit": unit,
                    "machine": machine,
                    "history": []
                }

            histories[key]["history"].append({
                "date": date.isoformat(),
                "games": games,
                "diff": diff,
                "bb": row.get("bb", 0),
                "rb": row.get("rb", 0)
            })

    result = []

    for item in histories.values():
        history = sorted(
            item["history"],
            key=lambda x: x["date"]
        )

        total_diff = sum(
            r["diff"] for r in history
        )

        positive_days = sum(
            1 for r in history if r["diff"] > 0
        )

        cumulative = 0

        for r in history:
            cumulative += r["diff"]
            r["cumulative_diff"] = cumulative

        item["history"] = history
        item["days"] = len(history)
        item["total_diff"] = total_diff
        item["avg_diff"] = round(
            total_diff / len(history)
        )
        item["positive_days"] = positive_days
        item["positive_rate"] = round(
            positive_days / len(history) * 100, 1
        )

        result.append(item)

    result.sort(
        key=lambda x: (x["unit"], x["machine"])
    )

    output = {
        "updated_at": datetime.now(JST).isoformat(),
        "store": "HYPER ARROW美原店",
        "lookback_days": LOOKBACK_DAYS,
        "total_days": len(dates),
        "total_units": len(result),
        "units": result
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

    print(
        f"履歴分析完了: {len(dates)}日、"
        f"{len(result)}台"
    )

if __name__ == "__main__":
    main()
