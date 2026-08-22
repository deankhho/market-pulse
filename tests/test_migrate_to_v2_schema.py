import json
from pathlib import Path

import pytest

from migrate_to_v2_schema import migrate


@pytest.fixture
def v1_history_file(tmp_path):
    v1_data = {
        "2026-08-20": {
            "contract_month": "202609",
            "contract_expiry_date": "2026-09-16",
            "session": "regular",
            "call_wall": 50000, "put_wall": 40000,
            "call_top3": [50000, 48000, 42000],
            "put_top3": [40000, 21800, 30000],
            "distribution": {"call": {"50000": 1569}, "put": {"40000": 906}},
            "twchips_commit": "010b4116149995704aba56db9cd2fd11ad157997",
            "pandas_version": "3.0.5",
        },
    }
    path = tmp_path / "oi_history.json"
    path.write_text(json.dumps(v1_data, ensure_ascii=False))
    return path


def test_migrate_produces_nested_schema(v1_history_file):
    migrate(v1_history_file)
    new_data = json.loads(v1_history_file.read_text())

    record = new_data["2026-08-20"]
    assert record["schema_version"] == 2
    assert record["session"] == "regular"
    assert record["twchips_commit"] == "010b4116149995704aba56db9cd2fd11ad157997"
    assert record["pandas_version"] == "3.0.5"
    assert record["weekly"] == {}

    near_month = record["near_month"]
    assert near_month["contract_month"] == "202609"
    assert near_month["contract_expiry_date"] == "2026-09-16"
    assert near_month["call_wall"] == 50000
    assert near_month["put_wall"] == 40000
    assert near_month["call_top3"] == [50000, 48000, 42000]
    assert near_month["put_top3"] == [40000, 21800, 30000]
    assert near_month["distribution"] == {"call": {"50000": 1569}, "put": {"40000": 906}}


def test_migrate_does_not_write_when_source_data_missing_field(tmp_path):
    """來源資料本身就缺必要欄位（例如壞掉的v1資料）→ migrate()在讀取
    NEAR_MONTH_FIELDS時直接KeyError，不會走到_atomic_write_json，
    檔案完全不受影響（因為根本沒開始寫）。"""
    broken_v1 = {
        "2026-08-20": {
            "contract_month": "202609",
            # 故意缺 contract_expiry_date 等其餘必要欄位
        },
    }
    path = tmp_path / "oi_history.json"
    path.write_text(json.dumps(broken_v1, ensure_ascii=False))

    with pytest.raises(KeyError):
        migrate(path)

    # 檔案內容完全沒被動過（migrate在組出near_month時就KeyError，
    # 根本沒有呼叫_atomic_write_json）
    assert json.loads(path.read_text()) == broken_v1
