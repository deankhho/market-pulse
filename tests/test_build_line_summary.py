import json
from build_line_summary import build_summary_text

def test_summary_same_month_reports_movement(tmp_path):
    (tmp_path / "oi_history.json").write_text(json.dumps({
        "2026-08-18": {
            "schema_version": 2, "session": "regular",
            "twchips_commit": "x", "pandas_version": "y",
            "near_month": {"contract_month": "202609", "call_wall": 24000, "put_wall": 23000,
                            "call_top3": [], "put_top3": [], "distribution": {"call": {}, "put": {}}},
            "weekly": {},
        },
        "2026-08-19": {
            "schema_version": 2, "session": "regular",
            "twchips_commit": "x", "pandas_version": "y",
            "near_month": {"contract_month": "202609", "call_wall": 24100, "put_wall": 23100,
                            "call_top3": [], "put_top3": [], "distribution": {"call": {}, "put": {}}},
            "weekly": {},
        },
    }))
    (tmp_path / "fetch_log.jsonl").write_text(
        '{"fetch_id":"a","state":"ok","reason":null,"resolved_data_date":"2026-08-19"}\n'
    )
    text = build_summary_text(tmp_path)
    assert "24000" in text and "24100" in text  # 較昨日位移數字都要出現
    assert "非投資建議" in text
    assert "壓力" not in text and "支撐" not in text  # 中性用語，不用壓力/支撐字眼

def test_summary_rollover_does_not_report_movement_number(tmp_path):
    """換月時改報換月事件，不計算跨日位移數字（spec核心要求）"""
    (tmp_path / "oi_history.json").write_text(json.dumps({
        "2026-08-18": {
            "schema_version": 2, "session": "regular",
            "twchips_commit": "x", "pandas_version": "y",
            "near_month": {"contract_month": "202608", "call_wall": 24000, "put_wall": 23000,
                            "call_top3": [], "put_top3": [], "distribution": {"call": {}, "put": {}}},
            "weekly": {},
        },
        "2026-08-19": {
            "schema_version": 2, "session": "regular",
            "twchips_commit": "x", "pandas_version": "y",
            "near_month": {"contract_month": "202609", "call_wall": 25000, "put_wall": 24000,
                            "call_top3": [], "put_top3": [], "distribution": {"call": {}, "put": {}}},
            "weekly": {},
        },
    }))
    (tmp_path / "fetch_log.jsonl").write_text(
        '{"fetch_id":"a","state":"ok","reason":null,"resolved_data_date":"2026-08-19"}\n'
    )
    text = build_summary_text(tmp_path)
    assert "已換月" in text
    assert "202608→202609" in text
    assert "→ 25000" not in text  # 不應該出現「24000 → 25000」這種跨合約位移描述

def test_summary_error_state_shows_stale_warning(tmp_path):
    (tmp_path / "oi_history.json").write_text(json.dumps({
        "2026-08-18": {
            "schema_version": 2, "session": "regular",
            "twchips_commit": "x", "pandas_version": "y",
            "near_month": {"contract_month": "202609", "call_wall": 24000, "put_wall": 23000,
                            "call_top3": [], "put_top3": [], "distribution": {"call": {}, "put": {}}},
            "weekly": {},
        },
    }))
    (tmp_path / "fetch_log.jsonl").write_text(
        '{"fetch_id":"a","state":"error","reason":"模擬失敗","resolved_data_date":null}\n'
    )
    text = build_summary_text(tmp_path)
    assert "抓取失敗" in text
    assert "2026-08-18" in text
