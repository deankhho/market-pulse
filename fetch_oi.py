"""Layer 3：唯一碰檔案/網路的地方。呼叫twchips→三態判斷→呼叫Layer1/2→寫兩份檔案。
spec: Layer 3 定義 + 資料模型章節。"""
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from calendar_utils import load_holidays
from contract_selection import NoValidContractError, select_contract
from market_observation import compute_observation
from validate import ABS_FLOOR, validate_chain


class UnexpectedFetchError(Exception):
    """預期外例外的包裝——讓main()知道要用非零exit code結束，
    不能被靜默吞成degraded事件（spec: exception處理原則，v5修正）。"""


# 預期內會發生、要降級成 state="error" 處理的例外類型
EXPECTED_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
    NoValidContractError,
)

# validate_chain() 本身可能因為上游資料格式異常而直接crash（Task4審查兩度確認的
# 已知限制：非數字字串觸發ValueError、無限值觸發OverflowError，validate_chain對
# 這類值只catch部分case，其餘會原生往外拋，牴觸它自己docstring承諾的
# 「回傳值讓呼叫端判定state=error」）。這裡在Layer3的整合邊界把它們當成
# 「資料本身壞掉」的預期內失敗處理，跟validate_chain回傳(False, reason)同一個
# 語意分類，不當成「程式bug」讓它變成unexpected往外炸。
# TypeError也一併攔下（防禦性）：屬於同一類「資料格式異常導致轉型失敗」，但
# 不同於前兩者，Task4審查沒有實際重現過會觸發TypeError的具體輸入，這裡沒有
# 對應測試——只是合理預期同一段程式碼也可能因為其他型別（如list/dict跑進float()）
# 觸發TypeError，屬未驗證分支。
VALIDATE_CRASH_EXCEPTIONS = (ValueError, OverflowError, TypeError)


def _atomic_write_json(path: Path, data: dict) -> None:
    """比照 fetch_par_value.py 的atomic write模式：寫暫存檔再os.replace。"""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    os.replace(tmp, path)


def _load_oi_history(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _append_fetch_log(path: Path, entry: dict) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def run(fetch_fn, data_dir: Path, holidays_path: Path, github_run_id: str) -> dict:
    """核心邏輯，fetch_fn注入方便測試（真實環境傳twchips.taifex.options_daily）。
    回傳寫入fetch_log的那筆entry，方便呼叫端/測試檢查結果。"""
    data_dir = Path(data_dir)
    fetch_log_path = data_dir / "fetch_log.jsonl"
    oi_history_path = data_dir / "oi_history.json"
    now_utc = datetime.now(timezone.utc)
    fetch_id = f"{now_utc.isoformat()}-{github_run_id}"

    holidays = load_holidays(str(holidays_path))
    today = date.today()

    def _log_and_return(state: str, reason: str | None, resolved_data_date: str | None):
        entry = {
            "fetch_id": fetch_id,
            "fetched_at_utc": now_utc.isoformat(),
            "state": state,
            "reason": reason,
            "resolved_data_date": resolved_data_date,
        }
        _append_fetch_log(fetch_log_path, entry)
        return entry

    try:
        chain_df = fetch_fn(today)
    except EXPECTED_EXCEPTIONS as e:
        return _log_and_return("error", f"{type(e).__name__}: {e}", None)

    if chain_df is None or chain_df.empty:
        if today in holidays:
            return _log_and_return("non_trading", None, None)
        return _log_and_return(
            "error", f"{today} 不在holidays.yaml清單內卻回傳空資料，可能是上游異常", None
        )

    try:
        ok, reason = validate_chain(chain_df, ABS_FLOOR)
    except VALIDATE_CRASH_EXCEPTIONS as e:
        # validate_chain對非數字/無限值等異常資料會直接crash（已知限制，見上方註解），
        # 這裡攔下轉成跟(False, reason)同語意的error事件，不讓它變成unexpected往外炸
        return _log_and_return(
            "error", f"欄位品質驗證時發生例外（資料格式異常）: {type(e).__name__}: {e}", None
        )
    if not ok:
        return _log_and_return("error", f"欄位品質驗證失敗: {reason}", None)

    # data_date一律取資料本身的交易日期欄位，不是抓取當下的系統日期（spec明確要求）
    data_date_raw = chain_df["交易日期"].iloc[0]
    data_date = pd.to_datetime(data_date_raw).date()

    try:
        contract_month, expiry_date, selection_reason = select_contract(
            chain_df, data_date, holidays
        )
    except NoValidContractError as e:
        return _log_and_return("error", f"合約選擇失敗: {e}", str(data_date))

    observation = compute_observation(chain_df, contract_month)

    # compute_observation對選中合約某一邊完全沒有列時，會靜默回傳wall=None/top3=[]
    # 而不是raise（已知限制，Task5審查兩度確認）。validate_chain是對「整條鏈」檢查
    # 買賣權雙邊都有出現，不保證「被選中的那個合約月份」雙邊都有列——所以這種殘缺
    # 觀測值有可能通過validate_chain卻在這裡出現。放行的話oi_history.json會寫入
    # put_wall/call_wall=null，看起來像是「今天沒有put wall」而非「資料不完整」，
    # 對後面的dashboard task是會誤導的假訊號。這裡當成跟validate_chain失敗同語意的
    # 預期內錯誤，不寫入歷史，讓lifecycle invariant保持成立。
    missing_sides = [
        side
        for side, wall in (("call", observation["call_wall"]), ("put", observation["put_wall"]))
        if wall is None
    ]
    if missing_sides:
        return _log_and_return(
            "error",
            f"合約 {contract_month} 的 {'/'.join(missing_sides)} 邊沒有任何列，"
            "無法計算wall（資料不完整）",
            str(data_date),
        )

    history = _load_oi_history(oi_history_path)
    history[str(data_date)] = {
        "contract_month": contract_month,
        "contract_expiry_date": str(expiry_date),
        "session": "regular",
        **observation,
        "twchips_commit": "010b4116149995704aba56db9cd2fd11ad157997",
        "pandas_version": pd.__version__,
    }
    _atomic_write_json(oi_history_path, history)

    return _log_and_return("ok", None, str(data_date))


def main():
    from twchips import taifex

    def real_fetch(d):
        return taifex.options_daily(d.isoformat(), product="TXO", session="regular")

    base = Path(__file__).parent
    github_run_id = os.environ.get("GITHUB_RUN_ID", "local")

    try:
        entry = run(real_fetch, base / "data", base / "data" / "holidays.yaml", github_run_id)
    except Exception as e:
        # 預期外例外：不吞、不寫成error事件，讓workflow真的失敗（spec: exception處理原則v5修正）
        print(f"::error::預期外例外，Layer3主流程未攔截: {type(e).__name__}: {e}", file=sys.stderr)
        raise UnexpectedFetchError(str(e)) from e

    print(f"完成: state={entry['state']}, reason={entry['reason']}")


if __name__ == "__main__":
    main()
