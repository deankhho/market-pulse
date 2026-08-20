import json
from gen_dashboard import build_dashboard_data, render_html


def test_build_dashboard_data_latest_observation_and_fetch_status(tmp_path):
    (tmp_path / "oi_history.json").write_text(json.dumps({
        "2026-08-18": {"contract_month": "202609", "call_wall": 24000, "put_wall": 23000,
                        "call_top3": [24000], "put_top3": [23000],
                        "distribution": {"call": {"24000": 100}, "put": {"23000": 90}}},
        "2026-08-19": {"contract_month": "202609", "call_wall": 24100, "put_wall": 23100,
                        "call_top3": [24100], "put_top3": [23100],
                        "distribution": {"call": {"24100": 110}, "put": {"23100": 95}}},
    }))
    (tmp_path / "fetch_log.jsonl").write_text(
        '{"fetch_id":"a","state":"ok","reason":null,"resolved_data_date":"2026-08-19"}\n'
    )

    data = build_dashboard_data(tmp_path)
    assert data["latest_observation_date"] == "2026-08-19"
    assert data["latest_fetch_state"] == "ok"
    assert data["rollover_events"] == []  # 兩天都是202609，沒有換月


def test_build_dashboard_data_detects_rollover(tmp_path):
    (tmp_path / "oi_history.json").write_text(json.dumps({
        "2026-08-18": {"contract_month": "202608", "call_wall": 24000, "put_wall": 23000,
                        "call_top3": [24000], "put_top3": [23000],
                        "distribution": {"call": {}, "put": {}}},
        "2026-08-19": {"contract_month": "202609", "call_wall": 25000, "put_wall": 24000,
                        "call_top3": [25000], "put_top3": [24000],
                        "distribution": {"call": {}, "put": {}}},
    }))
    (tmp_path / "fetch_log.jsonl").write_text(
        '{"fetch_id":"a","state":"ok","reason":null,"resolved_data_date":"2026-08-19"}\n'
    )
    data = build_dashboard_data(tmp_path)
    assert len(data["rollover_events"]) == 1
    assert data["rollover_events"][0]["from_month"] == "202608"
    assert data["rollover_events"][0]["to_month"] == "202609"

def test_render_html_shows_error_warning_not_for_non_trading(tmp_path):
    """error要顯示警示，non_trading不顯示（spec明確要求分開處理）"""
    base_data = {"history": {}, "sorted_dates": [], "latest_observation_date": "2026-08-18",
                 "latest_fetch_reason": None, "rollover_events": []}
    error_html = render_html({**base_data, "latest_fetch_state": "error"})
    assert "⚠️" in error_html

    non_trading_html = render_html({**base_data, "latest_fetch_state": "non_trading"})
    assert "⚠️" not in non_trading_html
