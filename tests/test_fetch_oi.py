import json
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from fetch_oi import run, UnexpectedFetchError


@pytest.fixture
def real_chain():
    return pd.read_csv("tests/fixtures/2026-08-19_regular.csv", dtype={"到期月份(週別)": str})


@pytest.fixture
def tmp_data_dir(tmp_path):
    holidays_path = tmp_path / "holidays.yaml"
    holidays_path.write_text("[]\n")  # 空清單，測試不需要真的假日
    return tmp_path


def test_run_ok_writes_both_files(real_chain, tmp_data_dir):
    """成功抓取：fetch_log多一行state=ok，oi_history也寫入這天的觀測值"""
    def fake_fetch(d):
        # 真實twchips回傳資料是2026-08-19的完整鏈，data_date從資料本身的
        # 交易日期欄位取，不是傳入的d
        return real_chain

    result = run(fake_fetch, tmp_data_dir, tmp_data_dir / "holidays.yaml", "run123")

    log_lines = (tmp_data_dir / "fetch_log.jsonl").read_text().strip().split("\n")
    assert len(log_lines) == 1
    log_entry = json.loads(log_lines[0])
    assert log_entry["state"] == "ok"
    assert "run123" in log_entry["fetch_id"]

    history = json.loads((tmp_data_dir / "oi_history.json").read_text())
    assert "2026-08-19" in history
    assert history["2026-08-19"]["contract_month"] == "202609"  # 202608到期週被排除


def test_run_non_trading_when_empty_and_in_holidays(tmp_data_dir):
    """空回傳＋在holidays.yaml清單內 → state=non_trading，不寫oi_history"""
    (tmp_data_dir / "holidays.yaml").write_text(f"[{date.today().isoformat()}]\n")

    def fake_empty_fetch(d):
        return pd.DataFrame()

    entry = run(fake_empty_fetch, tmp_data_dir, tmp_data_dir / "holidays.yaml", "run1")
    assert entry["state"] == "non_trading"
    assert not (tmp_data_dir / "oi_history.json").exists()


def test_run_error_when_empty_and_not_in_holidays(tmp_data_dir):
    """空回傳＋不在holidays.yaml清單內 → state=error（可能是上游異常，不是正常休市）"""
    def fake_empty_fetch(d):
        return pd.DataFrame()

    entry = run(fake_empty_fetch, tmp_data_dir, tmp_data_dir / "holidays.yaml", "run1")
    assert entry["state"] == "error"


def test_run_error_when_validation_fails(tmp_data_dir):
    """筆數不足ABS_FLOOR → state=error，不寫oi_history"""
    def fake_tiny_fetch(d):
        return pd.DataFrame({
            "到期月份(週別)": ["202609"], "契約到期日": ["20260916"],
            "履約價": [24000.0], "買賣權": ["買權"], "未沖銷契約數": [100.0],
            "交易日期": ["2026/08/19"],
        })

    entry = run(fake_tiny_fetch, tmp_data_dir, tmp_data_dir / "holidays.yaml", "run1")
    assert entry["state"] == "error"
    assert not (tmp_data_dir / "oi_history.json").exists()


def test_error_does_not_overwrite_existing_observation(real_chain, tmp_data_dir):
    """Lifecycle invariant：error/non_trading事件絕對不會讓oi_history.json裡
    已寫入的資料消失或變成null（spec: 錯誤處理／測試章節明確要求）"""
    def ok_fetch(d):
        return real_chain

    run(ok_fetch, tmp_data_dir, tmp_data_dir / "holidays.yaml", "run1")
    history_after_ok = json.loads((tmp_data_dir / "oi_history.json").read_text())
    assert "2026-08-19" in history_after_ok

    def fail_fetch(d):
        raise ConnectionError("模擬網路失敗")

    run(fail_fetch, tmp_data_dir, tmp_data_dir / "holidays.yaml", "run2")
    history_after_error = json.loads((tmp_data_dir / "oi_history.json").read_text())
    assert history_after_error == history_after_ok  # 完全沒被動過


def test_same_day_rerun_success_overwrites_same_key(real_chain, tmp_data_dir):
    """同一天重跑若又成功，直接覆蓋同一天的紀錄（更新的同日資料，不是抹掉），
    dict結構天然冪等，不會產生重複"""
    def ok_fetch(d):
        return real_chain

    run(ok_fetch, tmp_data_dir, tmp_data_dir / "holidays.yaml", "run1")
    run(ok_fetch, tmp_data_dir, tmp_data_dir / "holidays.yaml", "run2")

    history = json.loads((tmp_data_dir / "oi_history.json").read_text())
    assert len(history) == 1  # 還是只有一天，不是兩筆

    log_lines = (tmp_data_dir / "fetch_log.jsonl").read_text().strip().split("\n")
    assert len(log_lines) == 2  # 但fetch_log兩次執行都各記一行


def test_unexpected_exception_propagates_not_swallowed(tmp_data_dir):
    """預期外例外（非EXPECTED_EXCEPTIONS清單裡的型別）要往外拋，不能被run()吞掉
    寫成error事件（spec: exception處理原則v5修正，區分預期內/預期外）"""
    def buggy_fetch(d):
        raise TypeError("這是模擬的程式bug，不是網路問題")

    with pytest.raises(TypeError):
        run(buggy_fetch, tmp_data_dir, tmp_data_dir / "holidays.yaml", "run1")
    # 確認完全沒寫fetch_log——這種例外不屬於「三態」，run()本身就該讓它往外拋，
    # 由main()那層才負責印錯誤訊息+non-zero exit
    assert not (tmp_data_dir / "fetch_log.jsonl").exists()


# --- 以下兩則測試針對Task4/Task5審查已知的兩個限制，Task6整合時順手補上 ---

def test_run_error_when_validate_chain_raises_on_bad_data(tmp_data_dir):
    """validate_chain對非數字字串履約價會直接crash ValueError（Task4審查兩度確認的
    已知限制），而不是回傳(False, reason)。run()要把這種crash攔下轉成state=error，
    不能讓它變成unexpected往外炸（牴觸validate_chain自己docstring承諾的呼叫端契約）。"""
    def fake_bad_strike_fetch(d):
        df = pd.DataFrame({
            "到期月份(週別)": ["202609"] * 300, "契約到期日": ["20260916"] * 300,
            "履約價": [24000.0] * 300, "買賣權": (["買權", "賣權"] * 150),
            "未沖銷契約數": [100.0] * 300,
            "交易日期": ["2026/08/19"] * 300,
        })
        df = df.astype({"履約價": object})
        df.iloc[0, df.columns.get_loc("履約價")] = "abc"  # 非數字字串
        return df

    entry = run(fake_bad_strike_fetch, tmp_data_dir, tmp_data_dir / "holidays.yaml", "run1")
    assert entry["state"] == "error"
    assert not (tmp_data_dir / "oi_history.json").exists()


def test_run_error_when_selected_contract_missing_one_side(tmp_data_dir):
    """compute_observation對選中合約某一邊完全沒有列時，會靜默回傳wall=None/top3=[]
    而非raise（Task5審查兩度確認的已知限制）。validate_chain只檢查整條鏈買賣權雙邊
    都出現，不保證「被選中月份」雙邊都有列，所以這種殘缺資料有可能通過驗證。
    run()要擋下這種None wall，不寫進oi_history，避免dashboard看到一個
    「今天沒有put wall」的假訊號（其實是資料不完整，不是市場真的沒有put OI）。"""
    def fake_missing_put_fetch(d):
        rows = []
        for i in range(300):
            rows.append({
                "到期月份(週別)": "202609", "契約到期日": "20260916",
                "履約價": 24000.0 + i, "買賣權": "買權", "未沖銷契約數": 100.0,
                "交易日期": "2026/08/19",
            })
        # 補一筆賣權在別的（未被選中的）月份，讓validate_chain的VALID_SIDES檢查過關，
        # 但被選中的202609完全沒有賣權列
        rows.append({
            "到期月份(週別)": "202610", "契約到期日": "20261014",
            "履約價": 24000.0, "買賣權": "賣權", "未沖銷契約數": 100.0,
            "交易日期": "2026/08/19",
        })
        return pd.DataFrame(rows)

    entry = run(fake_missing_put_fetch, tmp_data_dir, tmp_data_dir / "holidays.yaml", "run1")
    assert entry["state"] == "error"
    assert not (tmp_data_dir / "oi_history.json").exists()
