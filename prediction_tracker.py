
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
NOW = datetime.now(JST)

DATA_DIR = Path("data")
DAILY_DIR = DATA_DIR / "arrow_mihara"
PREDICTION_DIR = DATA_DIR / "predictions"
RESULT_DIR = DATA_DIR / "prediction_results"

CURRENT_PREDICTION = (
    DATA_DIR / "arrow_mihara_tomorrow.json"
)
SUMMARY_OUTPUT = (
    DATA_DIR / "arrow_mihara_prediction_accuracy.json"
)


def read_json(path):
    try:
        return json.loads(
            path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return None


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


def average(values):
    return round(sum(values) / len(values), 1) if values else 0


def positive_rate(values):
    if not values:
        return 0

    return round(
        sum(v > 0 for v in values) / len(values) * 100,
        1
    )


def save_prediction():
    prediction = read_json(CURRENT_PREDICTION)

    if not isinstance(prediction, dict):
        print("予測データがないため保存をスキップ")
        return

    date = prediction.get("target_date")

    try:
        target = datetime.strptime(
            date, "%Y-%m-%d"
        ).date()
    except (TypeError, ValueError):
        print("予測対象日が不正です")
        return

    # 未来の予測のみを保存する
    if target <= NOW.date():
        print("過去または当日の予測なので保存しません")
        return

    path = PREDICTION_DIR / f"{date}.json"

    # 一度保存した予測は上書きしない
    # 後から有利な予測に書き換わるのを防ぐ
    if path.exists():
        print(f"予測保存済み: {date}")
        return

    write_json(path, prediction)
    print(f"予測を保存: {date}")


def normalize_daily(data):
    if not isinstance(data, list):
        return {}

    units = {}

    for item in data:
        try:
            unit = int(item["unit"])
            machine = str(item["machine"]).strip()
            games = int(item["games"])
            diff = int(item["diff"])
        except (KeyError, TypeError, ValueError):
            continue

        if not machine or games < 0:
            continue

        # 同じ台番号が重複する場合は最初の行を採用
        if unit not in units:
            units[unit] = {
                "unit": unit,
                "machine": machine,
                "games": games,
                "diff": diff
            }

    return units


def evaluate(date, prediction, daily):
    actual = normalize_daily(daily)

    if not actual:
        return None

    predicted = prediction.get(
        "unit_predictions", []
    )

    if not isinstance(predicted, list) or not predicted:
        return None

    # 予測順位をスコア順に確定
    predicted = sorted(
        predicted,
        key=lambda r: -float(r.get("score", 0))
    )

    matches = []

    for rank, item in enumerate(predicted, 1):
        try:
            unit = int(item["unit"])
            machine = str(item["machine"])
            score = float(item["score"])
        except (KeyError, TypeError, ValueError):
            continue

        row = actual.get(unit)

        # 台番号と機種の両方が一致する場合のみ照合
        if row is None or row["machine"] != machine:
            continue

        matches.append({
            "rank": rank,
            "unit": unit,
            "machine": machine,
            "prediction_score": score,
            "actual_diff": row["diff"],
            "actual_games": row["games"],
            "positive": row["diff"] > 0
        })

    # 当日データが一部しか取得できていない場合は
    # 照合件数を明示する
    def top_summary(limit):
        selected = [
            r for r in matches if r["rank"] <= limit
        ]

        diffs = [
            r["actual_diff"] for r in selected
        ]

        return {
            "predicted_count": min(
                limit, len(predicted)
            ),
            "matched_count": len(selected),
            "avg_diff": average(diffs),
            "positive_rate": positive_rate(diffs),
            "total_diff": sum(diffs)
        }

    store_diffs = [
        r["diff"] for r in actual.values()
    ]

    return {
        "date": date,
        "evaluated_at": NOW.isoformat(),
        "predicted_count": len(predicted),
        "matched_count": len(matches),
        "actual_unit_count": len(actual),
        "store_avg_diff": average(store_diffs),
        "store_positive_rate": positive_rate(
            store_diffs
        ),
        "top_5": top_summary(5),
        "top_10": top_summary(10),
        "top_20": top_summary(20),
        "matches": matches,
        "notes": [
            "プラス差枚を好成績として集計",
            "予測スコアは設定投入確率ではありません",
            "実際の差枚は高設定を証明しません",
            "照合できなかった台は成績集計から除外"
        ]
    }


def evaluate_saved_predictions():
    if not PREDICTION_DIR.exists():
        return

    for path in sorted(
        PREDICTION_DIR.glob("*.json")
    ):
        date = path.stem

        try:
            target = datetime.strptime(
                date, "%Y-%m-%d"
            ).date()
        except ValueError:
            continue

        # 当日が終了するまで評価しない
        if target >= NOW.date():
            continue

        daily_path = DAILY_DIR / f"{date}.json"

        if not daily_path.exists():
            print(f"実績待ち: {date}")
            continue

        prediction = read_json(path)
        daily = read_json(daily_path)

        if not isinstance(prediction, dict):
            continue

        result = evaluate(
            date, prediction, daily
        )

        if result is None:
            print(f"照合できるデータなし: {date}")
            continue

        output = RESULT_DIR / f"{date}.json"
        write_json(output, result)

        print(
            f"答え合わせ: {date} "
            f"上位10台 "
            f"{result['top_10']['matched_count']}台照合"
        )


def create_summary():
    results = []

    if RESULT_DIR.exists():
        for path in sorted(
            RESULT_DIR.glob("*.json")
        ):
            data = read_json(path)

            if isinstance(data, dict):
                results.append(data)

    results.sort(
        key=lambda r: r.get("date", ""),
        reverse=True
    )

    # 全件照合できた日だけを集計対象にする
    complete = [
        r for r in results
        if (
            r.get("top_10", {}).get("matched_count")
            == r.get("top_10", {}).get(
                "predicted_count"
            )
            and r.get("top_10", {}).get(
                "predicted_count", 0
            ) == 10
        )
    ]

    top10_diffs = [
        r["top_10"]["avg_diff"] for r in complete
    ]

    store_diffs = [
        r["store_avg_diff"] for r in complete
    ]

    summary = {
        "updated_at": NOW.isoformat(),
        "store": "HYPER ARROW美原店",
        "evaluated_days": len(results),
        "complete_top10_days": len(complete),
        "top10_avg_diff": average(top10_diffs),
        "store_avg_diff": average(store_diffs),
        "top10_advantage": round(
            average(top10_diffs) -
            average(store_diffs),
            1
        ) if complete else 0,
        "daily_results": results[:90],
        "notes": [
            "予測上位10台を全件照合できた日だけを平均に使用",
            "過去予測を保存した日以降の実績が対象",
            "サンプルが少ない期間の成績は参考値",
            "高設定の的中率を表すものではありません"
        ]
    }

    write_json(SUMMARY_OUTPUT, summary)

    print(
        f"答え合わせ集計完了: "
        f"{len(results)}日分"
    )


def main():
    save_prediction()
    evaluate_saved_predictions()
    create_summary()


if __name__ == "__main__":
    main()
