import json
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from fetch_oi import run, UnexpectedFetchError, _process_weekly_contracts


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
    assert history["2026-08-19"]["near_month"]["contract_month"] == "202609"  # 202608到期週被排除


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


def test_run_ok_writes_nested_schema_with_weekly(real_chain, tmp_data_dir):
    """成功路徑：near_month照舊寫入，weekly裡4檔（8/19真實fixture查證過
    的202608F3/W4/F4、202609W1）全部status=ok（fixture裡這4檔call/put都
    有OI資料），schema_version/session/twchips_commit/pandas_version在
    頂層，不在near_month或weekly底下。"""
    def fake_fetch(d):
        return real_chain

    run(fake_fetch, tmp_data_dir, tmp_data_dir / "holidays.yaml", "run1")

    history = json.loads((tmp_data_dir / "oi_history.json").read_text())
    record = history["2026-08-19"]

    assert record["schema_version"] == 2
    assert "session" in record
    assert "twchips_commit" in record
    assert "pandas_version" in record
    assert "session" not in record["near_month"]
    assert "twchips_commit" not in record["near_month"]

    assert record["near_month"]["contract_month"] == "202609"

    weekly = record["weekly"]
    assert set(weekly.keys()) == {"202608F3", "202608W4", "202608F4", "202609W1"}
    for cm in weekly:
        assert weekly[cm]["status"] == "ok"
        assert "call_wall" in weekly[cm]


def test_run_weekly_error_does_not_affect_near_month_or_other_weekly(monkeypatch, real_chain, tmp_data_dir):
    """單一週選處理失敗（模擬程式bug）→ 整個run()仍然成功寫入，近月
    資料完整，其他週選正常，只有出包那一檔標status=error（spec:
    「單一週選錯誤不影響整體」的端到端驗證）。"""
    import fetch_oi

    original = fetch_oi.compute_observation

    def selective_boom(chain_df, contract_month):
        if contract_month == "202608F3":
            raise KeyError("simulated bug")
        return original(chain_df, contract_month)

    monkeypatch.setattr(fetch_oi, "compute_observation", selective_boom)

    def fake_fetch(d):
        return real_chain

    entry = run(fake_fetch, tmp_data_dir, tmp_data_dir / "holidays.yaml", "run1")

    assert entry["state"] == "ok"  # 整體run()仍然成功
    history = json.loads((tmp_data_dir / "oi_history.json").read_text())
    record = history["2026-08-19"]
    assert record["near_month"]["contract_month"] == "202609"  # 近月不受影響
    assert record["weekly"]["202608F3"]["status"] == "error"
    assert record["weekly"]["202608W4"]["status"] == "ok"  # 其他週選正常


def test_run_lifecycle_invariant_holds_with_nested_schema(real_chain, tmp_data_dir):
    """既有lifecycle invariant（error事件不覆寫已成功寫入的資料）在新的
    巢狀格式下仍然成立——這是Task6就審查過的既有規則，這裡確認schema
    改變後沒有退化。"""
    def ok_fetch(d):
        return real_chain

    run(ok_fetch, tmp_data_dir, tmp_data_dir / "holidays.yaml", "run1")
    history_after_ok = json.loads((tmp_data_dir / "oi_history.json").read_text())

    def fail_fetch(d):
        raise ConnectionError("模擬網路失敗")

    run(fail_fetch, tmp_data_dir, tmp_data_dir / "holidays.yaml", "run2")
    history_after_error = json.loads((tmp_data_dir / "oi_history.json").read_text())
    assert history_after_error == history_after_ok


def test_process_weekly_contracts_status_ok(real_chain):
    """真實fixture裡202608F3這檔call/put都有OI資料，應該是status=ok，
    且完整帶出wall/top3/distribution。"""
    weekly_list = [("202608F3", date(2026, 8, 21))]
    result = _process_weekly_contracts(real_chain, weekly_list)

    assert result["202608F3"]["status"] == "ok"
    assert result["202608F3"]["contract_expiry_date"] == "2026-08-21"
    assert "call_wall" in result["202608F3"]
    assert "put_wall" in result["202608F3"]
    assert "call_top3" in result["202608F3"]
    assert "distribution" in result["202608F3"]
    assert "reason" not in result["202608F3"]


def test_process_weekly_contracts_status_error_on_ambiguous_expiry():
    """expiry_date為None（同代號多到期日異常）→ status=error，
    不呼叫compute_observation（不需要真的算wall）。"""
    weekly_list = [("202608F3", None)]
    result = _process_weekly_contracts(pd.DataFrame(), weekly_list)
    assert result["202608F3"]["status"] == "error"
    assert result["202608F3"]["reason"] == "同一代號對應多個到期日，資料異常"
    assert "contract_expiry_date" not in result["202608F3"]


def test_process_weekly_contracts_status_incomplete_on_missing_side():
    """合約存在但某一邊沒有任何列（compute_observation正常回傳wall=None）
    → status=incomplete，不是例外。"""
    fake_chain = pd.DataFrame({
        "到期月份(週別)": ["202608F3"],
        "契約到期日": ["20260821"],
        "履約價": [24000.0],
        "買賣權": ["買權"],  # 只有call，沒有put
        "未沖銷契約數": [100.0],
    })
    weekly_list = [("202608F3", date(2026, 8, 21))]
    result = _process_weekly_contracts(fake_chain, weekly_list)
    assert result["202608F3"]["status"] == "incomplete"
    assert result["202608F3"]["reason"] == "put邊沒有任何列，無法計算wall"
    assert result["202608F3"]["contract_expiry_date"] == "2026-08-21"
    assert "call_wall" not in result["202608F3"]


def test_process_weekly_contracts_status_error_on_unexpected_exception(monkeypatch, real_chain):
    """處理某一檔週選時發生未預期例外（模擬程式bug，非wall=None情況）
    → status=error，reason含例外類型，只影響這一檔，其他週選正常
    （spec: 「不偷偷吞掉未預期例外」跟「單一週選隔離」要同時成立）。"""
    import fetch_oi

    call_count = {"n": 0}
    original = fetch_oi.compute_observation

    def maybe_boom(chain_df, contract_month):
        call_count["n"] += 1
        if contract_month == "202608F3":
            raise KeyError("simulated bug")
        return original(chain_df, contract_month)

    monkeypatch.setattr(fetch_oi, "compute_observation", maybe_boom)

    weekly_list = [
        ("202608F3", date(2026, 8, 21)),
        ("202608W4", date(2026, 8, 26)),
    ]
    result = _process_weekly_contracts(real_chain, weekly_list)

    assert result["202608F3"]["status"] == "error"
    assert "KeyError" in result["202608F3"]["reason"]
    assert "simulated bug" in result["202608F3"]["reason"]
    # 第二檔沒受影響，正常算出status=ok（W4這檔在fixture裡call/put都有OI）
    assert result["202608W4"]["status"] == "ok"


# --- Finding 2 修復：list_weekly_contracts()/_process_weekly_contracts()對
# 全新的（非「代號多到期日」那個既有sentinel case）畸形資料仍可能raise
# （例如契約到期日不是合法%Y%m%d字串會讓pd.to_datetime丟ValueError），
# run()對這個呼叫要包try/except，讓當天near_month記錄照樣寫入、weekly
# 降級成{}，不能整天記錄都沒了。---

def test_run_survives_unparseable_weekly_expiry_date(real_chain, tmp_data_dir):
    """週選那一列的契約到期日欄位是無法解析的字串（如'N/A'），這會讓
    list_weekly_contracts()內部pd.to_datetime(...)直接拋ValueError（不是
    既有4輪外審已覆蓋的「同代號多到期日」sentinel case）。run()要把這個
    例外攔下：near_month正常寫入、weekly降級成{}、整體state仍是ok。"""
    bad_chain = real_chain.copy()
    bad_chain["契約到期日"] = bad_chain["契約到期日"].astype(object)
    bad_chain.loc[bad_chain["到期月份(週別)"] == "202608F3", "契約到期日"] = "N/A"

    def fake_fetch(d):
        return bad_chain

    entry = run(fake_fetch, tmp_data_dir, tmp_data_dir / "holidays.yaml", "run1")

    assert entry["state"] == "ok"
    history = json.loads((tmp_data_dir / "oi_history.json").read_text())
    record = history["2026-08-19"]
    assert record["near_month"]["contract_month"] == "202609"
    assert record["near_month"]["call_wall"] is not None
    assert record["near_month"]["put_wall"] is not None
    assert record["weekly"] == {}


def test_process_weekly_contracts_status_incomplete_both_sides():
    """雙邊都缺 → reason用「call/put兩邊都沒有任何列」範本，不是只提
    其中一邊（spec: reason範本雙邊都None的情況）。"""
    # chain_df裡完全沒有202608F3的任何列（只有另一個代號202609的一列，
    # 確保chain_df不是完全空的DataFrame——欄位還在，只是這個代號沒有列）。
    # 注意：brief原始寫法用pd.Series(dtype=...)混pd.concat組出空DataFrame，
    # 在本專案pandas版本下建構期就ValueError（scalar長度1 vs 空index長度0
    # 不相容），改用直接排除該代號的寫法達成同樣測試意圖。
    fake_chain = pd.DataFrame({
        "到期月份(週別)": ["202609"], "契約到期日": ["20260916"],
        "履約價": [24000.0], "買賣權": ["買權"], "未沖銷契約數": [1.0],
    })

    weekly_list = [("202608F3", date(2026, 8, 21))]
    result = _process_weekly_contracts(fake_chain, weekly_list)
    assert result["202608F3"]["status"] == "incomplete"
    assert result["202608F3"]["reason"] == "call/put兩邊都沒有任何列，無法計算wall"
