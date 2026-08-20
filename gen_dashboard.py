"""讀兩份資料檔（分開查詢，不共用同一個iterator——spec明確要求的實作陷阱提醒），
產出docs/index.html。"""
import json
from pathlib import Path


def build_dashboard_data(data_dir: Path) -> dict:
    """組裝前端需要的資料。latest_observation跟latest_fetch_status是兩個獨立查詢
    （spec: 第3輪外審ChatGPT指出這是實作時最容易誤植的地方）。"""
    history_path = data_dir / "oi_history.json"
    log_path = data_dir / "fetch_log.jsonl"

    history = json.loads(history_path.read_text()) if history_path.exists() else {}
    log_lines = log_path.read_text().strip().split("\n") if log_path.exists() else []
    latest_fetch = json.loads(log_lines[-1]) if log_lines and log_lines[-1] else None

    sorted_dates = sorted(history.keys())
    latest_observation_date = sorted_dates[-1] if sorted_dates else None

    # 換月事件偵測：逐日比對contract_month，不同就記一個rollover event，
    # 該處趨勢線要中斷（spec: 換月標記章節，三輪外審三家收斂的最重要發現）
    rollover_events = []
    for i in range(1, len(sorted_dates)):
        prev_date, cur_date = sorted_dates[i - 1], sorted_dates[i]
        prev_month = history[prev_date]["contract_month"]
        cur_month = history[cur_date]["contract_month"]
        if prev_month != cur_month:
            rollover_events.append({
                "date": cur_date, "from_month": prev_month, "to_month": cur_month,
            })

    return {
        "history": history,
        "sorted_dates": sorted_dates,
        "latest_observation_date": latest_observation_date,
        "latest_fetch_state": latest_fetch["state"] if latest_fetch else None,
        "latest_fetch_reason": latest_fetch["reason"] if latest_fetch else None,
        "rollover_events": rollover_events,
    }


def render_html(data: dict) -> str:
    """產出docs/index.html內容。用既有lightweight-charts，中性用語，
    non_trading與error分開顯示（spec明確要求，不能混在同一種警示文案）。"""
    warning_html = ""
    if data["latest_fetch_state"] == "error":
        warning_html = (
            f'<div class="warning">⚠️ 最新抓取異常，顯示為 '
            f'{data["latest_observation_date"]} 舊資料</div>'
        )
    # non_trading 不顯示警示（正常現象，spec明確要求）

    latest = data["history"].get(data["latest_observation_date"], {})

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>大盤盤勢分析</title>
<script src="vendor/lightweight-charts.js"></script>
<style>
body {{ font-family: sans-serif; margin: 2em; }}
.warning {{ background: #fff3cd; padding: 1em; border-radius: 4px; margin-bottom: 1em; }}
.disclaimer {{ color: #666; font-size: 0.9em; margin-top: 2em; }}
</style></head>
<body>
<h1>大盤盤勢分析</h1>
{warning_html}
<p>最新可用資料日期：{data["latest_observation_date"] or "無資料"}</p>
<p>Call OI集中履約價：{latest.get("call_wall", "—")}
   Put OI集中履約價：{latest.get("put_wall", "—")}</p>
<div id="chart"></div>
<script>
const rolloverEvents = {json.dumps(data["rollover_events"], ensure_ascii=False)};
const history = {json.dumps(data["history"], ensure_ascii=False)};
// TODO(下個任務): 用lightweight-charts畫逐日wall趨勢，rolloverEvents處中斷線＋標記
// 這裡先留資料注入點，圖表渲染細節由後續迭代補（不影響核心資料管線正確性）
</script>
<p class="disclaimer">僅供市場結構觀察，非投資建議。wall 可能因少量 OI 差異而變動，
不代表市場結構大幅改變。</p>
</body></html>"""


def main():
    base = Path(__file__).parent
    data = build_dashboard_data(base / "data")
    html = render_html(data)
    (base / "docs" / "index.html").write_text(html, encoding="utf-8")
    print(f"已產出 docs/index.html，最新資料日期: {data['latest_observation_date']}")


if __name__ == "__main__":
    main()
