"""一次性遷移腳本，把 data/oi_history.json 從v1扁平格式轉成v5巢狀格式。

用完即可刪除，不是production程式碼（比照Task1 capture_fixture.py慣例）。
"""
import json
from pathlib import Path

from fetch_oi import _atomic_write_json

NEAR_MONTH_FIELDS = [
    "contract_month", "contract_expiry_date",
    "call_wall", "put_wall", "call_top3", "put_top3", "distribution",
]
TOP_LEVEL_FIELDS = ["session", "twchips_commit", "pandas_version"]


def migrate(path: Path) -> None:
    """讀path指向的v1格式oi_history.json，轉成v5巢狀格式寫回同一個檔案。

    單一原子操作：整份讀取→記憶體轉換→驗證全部通過→一次atomic write。
    驗證失敗會拋AssertionError，不寫入，舊檔案完全不變（spec: 遷移驗證）。
    """
    old = json.loads(path.read_text())
    new = {}
    for data_date, record in old.items():
        near_month = {f: record[f] for f in NEAR_MONTH_FIELDS}
        new[data_date] = {
            "schema_version": 2,
            **{f: record[f] for f in TOP_LEVEL_FIELDS},
            "near_month": near_month,
            "weekly": {},
        }

    # 驗證：每個既有data_date的near_month完整dict＋頂層metadata都跟舊記錄
    # 完全相等，任一項不符就不寫入（spec: 遷移驗證比對「全部欄位值」，
    # 不是只比call_wall/put_wall）
    for data_date, record in old.items():
        migrated_near_month = new[data_date]["near_month"]
        for f in NEAR_MONTH_FIELDS:
            assert migrated_near_month[f] == record[f], (
                f"{data_date} 的 near_month.{f} 遷移後不一致"
            )
        for f in TOP_LEVEL_FIELDS:
            assert new[data_date][f] == record[f], (
                f"{data_date} 的頂層 {f} 遷移後不一致"
            )

    _atomic_write_json(path, new)
    print(f"遷移完成：{len(new)} 筆記錄轉成 schema_version=2")


if __name__ == "__main__":
    migrate(Path(__file__).parent / "data" / "oi_history.json")
