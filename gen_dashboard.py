"""讀兩份資料檔（分開查詢，不共用同一個iterator——spec明確要求的實作陷阱
提醒），產出docs/index.html。v5: 支援near_month/weekly巢狀結構，新增
週選lifecycle標籤計算（唯一負責的地方，Task8複用這裡的結果）。"""
import json
from datetime import date as date_cls
from pathlib import Path

# 終端態：合約已不在今天資料中，沒有status概念可言（不是「今天資料有問題」，
# 是「今天根本沒有這檔」）。渲染層要優先攔下這兩個值，不能落到status=="ok"
# 分支去讀根本不存在的call_top3/put_top3（Finding 1修復）。
TERMINAL_LIFECYCLES = ("依前次記錄推斷已到期", "前次記錄後消失（原因不明）")


def _weekly_lifecycle(
    today_weekly: dict, yesterday_weekly: dict,
    today_date_str: str, yesterday_date_str: str | None,
) -> dict:
    """計算週選lifecycle標籤（持續/首次觀測到/依前次記錄推斷已到期/
    前次記錄後消失原因不明）。status是次要註記，不是獨立分類——只要
    key今天存在，一律走「持續」或「首次觀測到」，status=error不會被
    誤判成消失（spec: lifecycle標籤章節，status三態的分類規則）。"""
    today_date = date_cls.fromisoformat(today_date_str)
    gap_days = (
        (today_date - date_cls.fromisoformat(yesterday_date_str)).days
        if yesterday_date_str else None
    )

    result = {}
    for cm, rec in today_weekly.items():
        lifecycle = "持續" if cm in yesterday_weekly else "首次觀測到"
        entry = {**rec, "lifecycle": lifecycle}
        if lifecycle == "持續" and gap_days and gap_days > 1:
            entry["gap_days"] = gap_days
        result[cm] = entry

    for cm, rec in yesterday_weekly.items():
        if cm in today_weekly:
            continue
        expiry_str = rec.get("contract_expiry_date")
        if expiry_str and date_cls.fromisoformat(expiry_str) < today_date:
            lifecycle = "依前次記錄推斷已到期"
        else:
            lifecycle = "前次記錄後消失（原因不明）"
        # 不把昨天的status複製過來（Finding 1核心修復）：這兩種終端態合約
        # 今天完全不存在，沒有call_top3/put_top3可言，"status"這個欄位在
        # 這裡沒有意義——留著昨天的"ok"只會誤導下游渲染走ok分支。
        result[cm] = {
            "contract_expiry_date": expiry_str,
            "lifecycle": lifecycle,
        }
    return result


def build_dashboard_data(data_dir: Path) -> dict:
    """組裝前端需要的資料。latest_observation跟latest_fetch_status是兩個
    獨立查詢（spec: 第3輪外審ChatGPT指出這是實作時最容易誤植的地方）。"""
    history_path = data_dir / "oi_history.json"
    log_path = data_dir / "fetch_log.jsonl"

    history = json.loads(history_path.read_text()) if history_path.exists() else {}
    log_lines = log_path.read_text().strip().split("\n") if log_path.exists() else []
    latest_fetch = json.loads(log_lines[-1]) if log_lines and log_lines[-1] else None

    sorted_dates = sorted(history.keys())
    latest_observation_date = sorted_dates[-1] if sorted_dates else None

    # 換月事件偵測：逐日比對近月contract_month，不同就記一個rollover event
    rollover_events = []
    for i in range(1, len(sorted_dates)):
        prev_date, cur_date = sorted_dates[i - 1], sorted_dates[i]
        prev_month = history[prev_date]["near_month"]["contract_month"]
        cur_month = history[cur_date]["near_month"]["contract_month"]
        if prev_month != cur_month:
            rollover_events.append({
                "date": cur_date, "from_month": prev_month, "to_month": cur_month,
            })

    weekly_lifecycle = {}
    if sorted_dates:
        idx = sorted_dates.index(latest_observation_date)
        today_weekly = history[latest_observation_date].get("weekly", {})
        if idx > 0:
            prev_date = sorted_dates[idx - 1]
            yesterday_weekly = history[prev_date].get("weekly", {})
            weekly_lifecycle = _weekly_lifecycle(
                today_weekly, yesterday_weekly, latest_observation_date, prev_date
            )
        else:
            weekly_lifecycle = _weekly_lifecycle(
                today_weekly, {}, latest_observation_date, None
            )

    return {
        "history": history,
        "sorted_dates": sorted_dates,
        "latest_observation_date": latest_observation_date,
        "latest_fetch_state": latest_fetch["state"] if latest_fetch else None,
        "latest_fetch_reason": latest_fetch["reason"] if latest_fetch else None,
        "rollover_events": rollover_events,
        "weekly_lifecycle": weekly_lifecycle,
    }


def _sort_weekly_items(weekly_lifecycle: dict) -> list:
    """依contract_expiry_date由小到大排序，同到期日依代號字串排序，
    None(異常/未知)排最後（spec: 排序規則）。"""
    def key(item):
        cm, entry = item
        expiry = entry.get("contract_expiry_date")
        return (expiry is None, expiry or "9999-99-99", cm)
    return sorted(weekly_lifecycle.items(), key=key)


def _render_weekly_row(contract_month: str, entry: dict) -> str:
    status = entry.get("status")
    lifecycle = entry.get("lifecycle", "")
    if lifecycle in TERMINAL_LIFECYCLES:
        # 終端態：合約今天已不存在，沒有Call/Put可顯示，不能落到ok/incomplete
        # 分支去印出佔位符或空白bracket（Finding 1驗收標準）。
        return f"<li>{contract_month}［{lifecycle}］（已不在追蹤範圍，無最新Call/Put資料）</li>"
    if status == "ok":
        top3c = entry.get("call_top3", [])
        top3p = entry.get("put_top3", [])
        call_top2 = f"（次大 {top3c[1]}）" if len(top3c) >= 2 else ""
        put_top2 = f"（次大 {top3p[1]}）" if len(top3p) >= 2 else ""
        return (
            f"<li>{contract_month}［{lifecycle}］"
            f"Call {top3c[0] if top3c else '—'}{call_top2}／"
            f"Put {top3p[0] if top3p else '—'}{put_top2}</li>"
        )
    reason = entry.get("reason", "")
    return f"<li>{contract_month}［{lifecycle}／{status}］{reason}</li>"


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

    latest_record = data["history"].get(data["latest_observation_date"], {})
    latest = latest_record.get("near_month", {})
    call_top3 = latest.get("call_top3", [])
    put_top3 = latest.get("put_top3", [])
    call_top2 = f"（次大 {call_top3[1]}）" if len(call_top3) >= 2 else ""
    put_top2 = f"（次大 {put_top3[1]}）" if len(put_top3) >= 2 else ""

    weekly_lifecycle = data.get("weekly_lifecycle", {})
    weekly_rows = "".join(
        _render_weekly_row(cm, entry)
        for cm, entry in _sort_weekly_items(weekly_lifecycle)
    )
    weekly_html = f"<ul>{weekly_rows}</ul>" if weekly_rows else "<p>（尚無週選資料）</p>"

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
<h2>近月</h2>
<p>Call OI集中履約價：{call_top3[0] if call_top3 else "—"}{call_top2}
   Put OI集中履約價：{put_top3[0] if put_top3 else "—"}{put_top2}</p>
<h2>週選</h2>
{weekly_html}
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
