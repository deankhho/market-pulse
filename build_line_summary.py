"""產出LINE reply用的中性措辭摘要文字，GAS relay直接讀這個檔案的內容當
reply（比照hourly_report.py的--publish模式）。v5: 近月顯示top1+top2，
新增週選區塊（複用gen_dashboard.py算好的lifecycle標籤，不重新實作）。"""
from pathlib import Path

from gen_dashboard import build_dashboard_data

DISCLAIMER = (
    "僅供市場結構觀察，非投資建議。wall 可能因少量 OI 差異而變動，"
    "不代表市場結構大幅改變。"
)
WEEKLY_LINE_CAP = 8  # spec: LINE週選區塊最多顯示8行


def _top2_suffix(top3: list) -> str:
    return f"（次大：{top3[1]}）" if len(top3) >= 2 else ""


def _format_weekly_line(contract_month: str, entry: dict) -> str:
    status = entry.get("status")
    lifecycle = entry.get("lifecycle", "")
    if status == "ok":
        top3c = entry.get("call_top3", [])
        top3p = entry.get("put_top3", [])
        return (
            f"・{contract_month}[{lifecycle}] "
            f"Call{top3c[0] if top3c else '—'}{_top2_suffix(top3c)}／"
            f"Put{top3p[0] if top3p else '—'}{_top2_suffix(top3p)}"
        )
    reason = entry.get("reason", "")
    return f"・{contract_month}[{lifecycle}/{status}] {reason}"


def _weekly_section(weekly_lifecycle: dict) -> str:
    """依到期日排序，異常訊號（前次記錄後消失/status=error）優先排進
    前8行，超過用「等N檔」收尾（spec: LINE訊息長度限制）。"""
    if not weekly_lifecycle:
        return ""

    def sort_key(item):
        cm, entry = item
        expiry = entry.get("contract_expiry_date")
        is_anomaly = (
            entry.get("lifecycle") == "前次記錄後消失（原因不明）"
            or entry.get("status") == "error"
        )
        return (0 if is_anomaly else 1, expiry is None, expiry or "9999-99-99", cm)

    items = sorted(weekly_lifecycle.items(), key=sort_key)
    shown = items[:WEEKLY_LINE_CAP]
    lines = [_format_weekly_line(cm, entry) for cm, entry in shown]
    if len(items) > WEEKLY_LINE_CAP:
        lines.append(f"...等{len(items) - WEEKLY_LINE_CAP}檔（詳見儀表板）")

    incomplete_count = sum(
        1 for e in weekly_lifecycle.values() if e.get("status") in ("incomplete", "error")
    )
    if incomplete_count:
        lines.append(f"（{incomplete_count}檔週選資料不完整／異常）")

    return "\n".join(lines)


def build_summary_text(data_dir: Path) -> str:
    data = build_dashboard_data(data_dir)

    if data["latest_fetch_state"] == "error":
        latest = data["history"].get(data["latest_observation_date"], {}).get("near_month", {})
        return (
            f"⚠️ 今日抓取失敗，以下為 {data['latest_observation_date']} 資料\n"
            f"Call OI集中履約價：{latest.get('call_wall', '—')}\n"
            f"Put OI集中履約價：{latest.get('put_wall', '—')}\n"
            f"{DISCLAIMER}"
        )

    sorted_dates = data["sorted_dates"]
    if not sorted_dates:
        return f"目前無可用資料。\n{DISCLAIMER}"

    latest_date = sorted_dates[-1]
    latest = data["history"][latest_date]["near_month"]

    prev_date = sorted_dates[-2] if len(sorted_dates) >= 2 else None
    prev = data["history"][prev_date]["near_month"] if prev_date else None

    call_top3 = latest.get("call_top3", [])
    put_top3 = latest.get("put_top3", [])

    if prev is None:
        movement_line = "（首日資料，暫無前日可比）"
    elif prev["contract_month"] != latest["contract_month"]:
        movement_line = (
            f"⚙️ 已換月（{prev['contract_month']}→{latest['contract_month']}），"
            f"趨勢重新起算"
        )
    else:
        movement_line = (
            f"較昨日：Call OI集中點 {prev['call_wall']} → {latest['call_wall']}，"
            f"Put OI集中點 {prev['put_wall']} → {latest['put_wall']}"
        )

    weekly_text = _weekly_section(data.get("weekly_lifecycle", {}))
    weekly_block = f"\n{weekly_text}" if weekly_text else ""

    return (
        f"【大盤盤勢】{latest_date}\n"
        f"Call OI集中履約價：{latest['call_wall']}{_top2_suffix(call_top3)}\n"
        f"Put OI集中履約價：{latest['put_wall']}{_top2_suffix(put_top3)}\n"
        f"{movement_line}"
        f"{weekly_block}\n"
        f"{DISCLAIMER}"
    )


def main():
    base = Path(__file__).parent
    text = build_summary_text(base / "data")
    (base / "data" / "line_latest.txt").write_text(text, encoding="utf-8")
    print("已產出 data/line_latest.txt")
    print("---")
    print(text)


if __name__ == "__main__":
    main()
