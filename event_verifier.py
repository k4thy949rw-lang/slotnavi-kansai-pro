
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path("data")
CANDIDATES = ROOT / "mihara_event_candidates.json"
MANUAL = ROOT / "mihara_events.json"
DAILY = ROOT / "arrow_mihara"
OUTPUT = ROOT / "mihara_event_verification.json"

JST = ZoneInfo("Asia/Tokyo")


def read_json(path, default):
    try:
        return json.loads(
            path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return default


def valid_date(value):
    try:
        return (
            datetime.strptime(
                value, "%Y-%m-%d"
            ).date().isoformat() == value
        )
    except (TypeError, ValueError):
        return False


def key(event):
    return (
        event["date"],
        event["type"],
        event["name"]
    )


def load_events(path):
    data = read_json(path, [])

    if not isinstance(data, list):
        return []

    result = []

    for item in data:
        if not isinstance(item, dict):
            continue

        date = item.get("date")
        name = str(item.get("name", "")).strip()
        kind = str(item.get("type", "")).strip()

        if not valid_date(date):
            continue

        if not name or not kind:
            continue

        if name == "イベント登録テスト":
            continue

        result.append({
            **item,
            "date": date,
            "name": name,
            "type": kind
        })

    return result


def daily_status(date):
    path = DAILY / f"{date}.json"

    if not path.exists():
        return {
            "actual_available": False,
            "actual_units": 0
        }

    data = read_json(path, [])

    if not isinstance(data, list):
        return {
            "actual_available": False,
            "actual_units": 0
        }

    units = set()

    for row in data:
        if not isinstance(row, dict):
            continue

        try:
            unit = int(row["unit"])
            int(row["diff"])
            int(row["games"])
        except (KeyError, ValueError, TypeError):
            continue

        units.add(unit)

    return {
        "actual_available": bool(units),
        "actual_units": len(units)
    }


def main():
    now = datetime.now(JST)
    today = now.date().isoformat()

    automatic = load_events(CANDIDATES)
    manual = load_events(MANUAL)

    manual_map = {
        key(event): event
        for event in manual
    }

    all_events = {}

    for event in automatic:
        all_events[key(event)] = event

    for event in manual:
        all_events[key(event)] = event

    rows = []

    for event_key, event in sorted(
        all_events.items()
    ):
        date, kind, name = event_key

        matching_manual = manual_map.get(
            event_key
        )

        # 開催確認は明示的な記録のみ採用
        confirmed = (
            event.get("status") == "confirmed"
        )

        actual = daily_status(date)

        if date > today:
            period = "future"
        elif date == today:
            period = "today"
        else:
            period = "past"

        if confirmed and actual["actual_available"]:
            analysis_ready = True
            reason = "開催確認済み・差枚実績あり"
        elif confirmed:
            analysis_ready = False
            reason = "開催確認済み・差枚実績待ち"
        elif actual["actual_available"]:
            analysis_ready = False
            reason = "差枚実績あり・開催未確認"
        else:
            analysis_ready = False
            reason = "開催未確認・差枚実績なし"

        # 告知掲載と実際の開催を区別する
        last_seen = str(event.get("last_collected_at") or "")
        listed_on_event_day = last_seen[:10] == date
        listing_status = (
            "当日掲載確認" if listed_on_event_day
            else "掲載履歴あり" if event.get("source")
            else "掲載情報なし"
        )

        rows.append({
            "date": date,
            "name": name,
            "type": kind,
            "status": (
                "confirmed"
                if confirmed else "unverified"
            ),
            "period": period,
            "analysis_ready": analysis_ready,
            "reason": reason,
            "actual_available": actual[
                "actual_available"
            ],
            "actual_units": actual[
                "actual_units"
            ],
            "source": event.get("source", ""),
            "first_seen": event.get(
                "first_seen"
            ),
            "last_collected_at": event.get(
                "last_collected_at"
            ),
            "seen_count": event.get(
                "seen_count", 0
            ),
            "listing_status": listing_status,
            "listed_on_event_day": listed_on_event_day,
            "manual_record": (
                matching_manual is not None
            )
        })

    result = {
        "updated_at": now.isoformat(),
        "store": "HYPER ARROW美原店",
        "total_events": len(rows),
        "confirmed_events": sum(
            row["status"] == "confirmed"
            for row in rows
        ),
        "analysis_ready_events": sum(
            row["analysis_ready"]
            for row in rows
        ),
        "unverified_with_actual": sum(
            row["status"] == "unverified"
            and row["actual_available"]
            for row in rows
        ),
        "events": rows,
        "notes": [
            "差枚実績の存在はイベント開催の証拠ではない",
            "取得回数は独立した開催確認ではない",
            "確認済み状態は明示的な記録のみ採用",
            "開催確認済みかつ差枚実績ありを分析可能とする",
            "イベントの実績差は将来の勝率を保証しない"
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

    print("イベント照合完了")
    print("登録イベント:", result["total_events"])
    print(
        "確認済み:",
        result["confirmed_events"]
    )
    print(
        "分析可能:",
        result["analysis_ready_events"]
    )
    print(
        "実績あり・開催未確認:",
        result["unverified_with_actual"]
    )


if __name__ == "__main__":
    main()
