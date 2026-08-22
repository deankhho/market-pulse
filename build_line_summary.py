"""產出LINE reply用的中性措辭摘要文字，GAS relay直接讀這個檔案的內容當reply
（比照hourly_report.py的--publish模式：build→存檔→commit push→GAS讀reply）。"""
from pathlib import Path

from gen_dashboard import build_dashboard_data

DISCLAIMER = (
    "僅供市場結構觀察，非投資建議。wall 可能因少量 OI 差異而變動，"
    "不代表市場結構大幅改變。"
)


def build_summary_text(data_dir: Path) -> str:
    data = build_dashboard_data(data_dir)

    if data["latest_fetch_state"] == "error":
        latest_record = data["history"].get(data["latest_observation_date"], {})
        latest = latest_record.get("near_month", {})
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

    return (
        f"【大盤盤勢】{latest_date}\n"
        f"Call OI集中履約價：{latest['call_wall']}\n"
        f"Put OI集中履約價：{latest['put_wall']}\n"
        f"{movement_line}\n"
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
