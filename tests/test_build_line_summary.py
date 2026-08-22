import json
from build_line_summary import build_summary_text

def test_summary_same_month_reports_movement_and_top2(tmp_path):
    (tmp_path / "oi_history.json").write_text(json.dumps({
        "2026-08-18": {
            "schema_version": 2, "session": "regular",
            "twchips_commit": "x", "pandas_version": "y",
            "near_month": {
                "contract_month": "202609", "call_wall": 24000, "put_wall": 23000,
                "call_top3": [24000, 23900], "put_top3": [23000, 22900],
                "distribution": {"call": {}, "put": {}},
            },
            "weekly": {},
        },
        "2026-08-19": {
            "schema_version": 2, "session": "regular",
            "twchips_commit": "x", "pandas_version": "y",
            "near_month": {
                "contract_month": "202609", "call_wall": 24100, "put_wall": 23100,
                "call_top3": [24100, 24000], "put_top3": [23100, 23000],
                "distribution": {"call": {}, "put": {}},
            },
            "weekly": {},
        },
    }))
    (tmp_path / "fetch_log.jsonl").write_text(
        '{"fetch_id":"a","state":"ok","reason":null,"resolved_data_date":"2026-08-19"}\n'
    )
    text = build_summary_text(tmp_path)
    assert "24000" in text and "24100" in text  # 較昨日位移數字都要出現
    assert "次大：24000" in text  # 今天call的次大是24000
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

def test_summary_weekly_section_anomaly_prioritized_in_cap(tmp_path):
    """週選區塊最多8行，「前次記錄後消失」異常訊號即使到期日較晚也要
    優先排進前8行（spec: LINE長度限制，異常優先）。"""
    today_weekly = {}
    for i in range(9):
        cm = f"20260{8+i//9}F{i+1}"
        today_weekly[cm] = {
            "status": "ok", "contract_expiry_date": f"2026-08-{21+i:02d}",
            "call_wall": 24000 + i, "put_wall": 23000 + i,
            "call_top3": [24000 + i], "put_top3": [23000 + i],
            "distribution": {"call": {}, "put": {}},
        }
    yesterday_weekly = dict(today_weekly)
    # 昨天多一檔，今天消失，到期日設在很後面（不會被自然排進前8名）
    yesterday_weekly["202609W9"] = {
        "status": "ok", "contract_expiry_date": "2026-09-30",
        "call_wall": 1, "put_wall": 1, "call_top3": [1], "put_top3": [1],
        "distribution": {"call": {}, "put": {}},
    }

    (tmp_path / "oi_history.json").write_text(json.dumps({
        "2026-08-18": {
            "schema_version": 2, "session": "regular",
            "twchips_commit": "x", "pandas_version": "y",
            "near_month": {
                "contract_month": "202609", "call_wall": 50000, "put_wall": 40000,
                "call_top3": [50000], "put_top3": [40000],
                "distribution": {"call": {}, "put": {}},
            },
            "weekly": yesterday_weekly,
        },
        "2026-08-19": {
            "schema_version": 2, "session": "regular",
            "twchips_commit": "x", "pandas_version": "y",
            "near_month": {
                "contract_month": "202609", "call_wall": 50100, "put_wall": 40100,
                "call_top3": [50100], "put_top3": [40100],
                "distribution": {"call": {}, "put": {}},
            },
            "weekly": today_weekly,
        },
    }))
    (tmp_path / "fetch_log.jsonl").write_text(
        '{"fetch_id":"a","state":"ok","reason":null,"resolved_data_date":"2026-08-19"}\n'
    )
    text = build_summary_text(tmp_path)
    assert "202609W9" in text  # 消失的異常訊號被優先排進顯示範圍
    assert "等" in text and "檔（詳見儀表板）" in text
