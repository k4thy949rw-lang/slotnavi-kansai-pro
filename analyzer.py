
import json
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")

DATA_DIR = Path("data/arrow_mihara")
OUTPUT = Path("data/arrow_mihara_ranking.json")

# 直近30日を分析対象にする
LOOKBACK_DAYS = 30
MIN_DAYS = 3


def load_data():
    today = datetime.now(JST).date()
    records = []

    if not DATA_DIR.exists():
        return records

    for path in DATA_DIR.glob("????-??-??.json"):
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

            if isinstance(data, list):
                records.extend(data)

        except (ValueError, json.JSONDecodeError):
            print(f"読み込み失敗: {path}")

    return records


def analyze(records):
    grouped = defaultdict(list)

    for r in records:
        try:
            unit = int(r["unit"])
            games = int(r["games"])
            diff = int(r["diff"])
            day = r["date"]
            machine = r["machine"]

            if games < 0:
                continue

            grouped[(unit, machine)].append({
                "date": day,
                "games": games,
                "diff": diff
            })

        except (KeyError, ValueError, TypeError):
            continue

    ranking = []

    for (unit, machine), rows in grouped.items():
        # 同一日・同一台の重複を除外
        by_date = {
            row["date"]: row
            for row in rows
        }

        rows = list(by_date.values())
        days = len(rows)

        total_games = sum(r["games"] for r in rows)
        total_diff = sum(r["diff"] for r in rows)

        if days < MIN_DAYS or total_games == 0:
            continue

        avg_diff = total_diff / days
        avg_games = total_games / days

        positive_days = sum(
            1 for r in rows if r["diff"] > 0
        )

        win_rate = positive_days / days * 100

        # スコアは過去の実績を比較するための指標
        # 設定を示す確率ではない
        score = (
            min(max(avg_diff / 20, -50), 50)
            + win_rate * 0.3
            + min(avg_games / 300, 20)
        )

        ranking.append({
            "unit": unit,
            "machine": machine,
            "days": days,
            "avg_diff": round(avg_diff),
            "avg_games": round(avg_games),
            "win_rate": round(win_rate, 1),
            "score": round(score, 1)
        })

    ranking.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    return ranking


def main():
    records = load_data()
    ranking = analyze(records)

    result = {
        "updated_at": datetime.now(JST).isoformat(),
        "store": "HYPER ARROW美原店",
        "analysis_days": LOOKBACK_DAYS,
        "minimum_days": MIN_DAYS,
        "ranked_units": len(ranking),
        "ranking": ranking
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

    print(f"分析対象: {len(records)}件")
    print(f"ランキング作成: {len(ranking)}台")

    if not ranking:
        print(
            "分析データが不足しています。"
            "同じ台番号のデータを3日以上蓄積してください。"
        )
    else:
        for i, row in enumerate(ranking[:10], 1):
            print(
                f"{i}位: {row['unit']}番台 "
                f"{row['machine']} "
                f"スコア{row['score']}"
            )


if __name__ == "__main__":
    main()
