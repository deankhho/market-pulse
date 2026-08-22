import json
from gen_dashboard import (
    TERMINAL_LIFECYCLES,
    _render_weekly_row,
    _weekly_lifecycle,
    build_dashboard_data,
    render_html,
)


def test_build_dashboard_data_latest_observation_and_fetch_status(tmp_path):
    (tmp_path / "oi_history.json").write_text(json.dumps({
        "2026-08-18": {
            "schema_version": 2, "session": "regular",
            "twchips_commit": "x", "pandas_version": "y",
            "near_month": {
                "contract_month": "202609", "call_wall": 24000, "put_wall": 23000,
                "call_top3": [24000], "put_top3": [23000],
                "distribution": {"call": {"24000": 100}, "put": {"23000": 90}},
            },
            "weekly": {},
        },
        "2026-08-19": {
            "schema_version": 2, "session": "regular",
            "twchips_commit": "x", "pandas_version": "y",
            "near_month": {
                "contract_month": "202609", "call_wall": 24100, "put_wall": 23100,
                "call_top3": [24100], "put_top3": [23100],
                "distribution": {"call": {"24100": 110}, "put": {"23100": 95}},
            },
            "weekly": {},
        },
    }))
    (tmp_path / "fetch_log.jsonl").write_text(
        '{"fetch_id":"a","state":"ok","reason":null,"resolved_data_date":"2026-08-19"}\n'
    )

    data = build_dashboard_data(tmp_path)
    assert data["latest_observation_date"] == "2026-08-19"
    assert data["latest_fetch_state"] == "ok"
    assert data["rollover_events"] == []


def test_build_dashboard_data_detects_rollover(tmp_path):
    (tmp_path / "oi_history.json").write_text(json.dumps({
        "2026-08-18": {
            "schema_version": 2, "session": "regular",
            "twchips_commit": "x", "pandas_version": "y",
            "near_month": {
                "contract_month": "202608", "call_wall": 24000, "put_wall": 23000,
                "call_top3": [24000], "put_top3": [23000],
                "distribution": {"call": {}, "put": {}},
            },
            "weekly": {},
        },
        "2026-08-19": {
            "schema_version": 2, "session": "regular",
            "twchips_commit": "x", "pandas_version": "y",
            "near_month": {
                "contract_month": "202609", "call_wall": 25000, "put_wall": 24000,
                "call_top3": [25000], "put_top3": [24000],
                "distribution": {"call": {}, "put": {}},
            },
            "weekly": {},
        },
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
    base_data = {
        "history": {}, "sorted_dates": [], "latest_observation_date": "2026-08-18",
        "latest_fetch_reason": None, "rollover_events": [], "weekly_lifecycle": {},
    }
    error_html = render_html({**base_data, "latest_fetch_state": "error"})
    assert "⚠️" in error_html

    non_trading_html = render_html({**base_data, "latest_fetch_state": "non_trading"})
    assert "⚠️" not in non_trading_html


def test_build_dashboard_data_reads_nested_near_month(tmp_path):
    """v5巢狀格式下，latest_observation_date/rollover偵測要改讀
    history[date]["near_month"]["contract_month"]，不是舊的扁平格式。"""
    (tmp_path / "oi_history.json").write_text(json.dumps({
        "2026-08-20": {
            "schema_version": 2, "session": "regular",
            "twchips_commit": "x", "pandas_version": "y",
            "near_month": {
                "contract_month": "202609", "call_wall": 24000, "put_wall": 23000,
                "call_top3": [24000], "put_top3": [23000],
                "distribution": {"call": {}, "put": {}},
            },
            "weekly": {},
        },
        "2026-08-21": {
            "schema_version": 2, "session": "regular",
            "twchips_commit": "x", "pandas_version": "y",
            "near_month": {
                "contract_month": "202609", "call_wall": 24100, "put_wall": 23100,
                "call_top3": [24100], "put_top3": [23100],
                "distribution": {"call": {}, "put": {}},
            },
            "weekly": {},
        },
    }))
    (tmp_path / "fetch_log.jsonl").write_text(
        '{"fetch_id":"a","state":"ok","reason":null,"resolved_data_date":"2026-08-21"}\n'
    )
    data = build_dashboard_data(tmp_path)
    assert data["latest_observation_date"] == "2026-08-21"
    assert data["rollover_events"] == []


def test_weekly_lifecycle_continuing_and_first_observed(tmp_path):
    """同代號兩天都有 → 持續；只有今天有 → 首次觀測到。"""
    (tmp_path / "oi_history.json").write_text(json.dumps({
        "2026-08-20": {
            "schema_version": 2, "session": "regular",
            "twchips_commit": "x", "pandas_version": "y",
            "near_month": {"contract_month": "202609", "call_wall": 24000,
                            "put_wall": 23000, "call_top3": [24000], "put_top3": [23000],
                            "distribution": {"call": {}, "put": {}}},
            "weekly": {
                "202608F3": {"status": "ok", "contract_expiry_date": "2026-08-21",
                              "call_wall": 24000, "put_wall": 23000,
                              "call_top3": [24000], "put_top3": [23000],
                              "distribution": {"call": {}, "put": {}}},
            },
        },
        "2026-08-21": {
            "schema_version": 2, "session": "regular",
            "twchips_commit": "x", "pandas_version": "y",
            "near_month": {"contract_month": "202609", "call_wall": 24100,
                            "put_wall": 23100, "call_top3": [24100], "put_top3": [23100],
                            "distribution": {"call": {}, "put": {}}},
            "weekly": {
                "202608F3": {"status": "ok", "contract_expiry_date": "2026-08-21",
                              "call_wall": 24100, "put_wall": 23100,
                              "call_top3": [24100], "put_top3": [23100],
                              "distribution": {"call": {}, "put": {}}},
                "202608F4": {"status": "ok", "contract_expiry_date": "2026-08-28",
                              "call_wall": 500, "put_wall": 400,
                              "call_top3": [500], "put_top3": [400],
                              "distribution": {"call": {}, "put": {}}},
            },
        },
    }))
    (tmp_path / "fetch_log.jsonl").write_text(
        '{"fetch_id":"a","state":"ok","reason":null,"resolved_data_date":"2026-08-21"}\n'
    )
    data = build_dashboard_data(tmp_path)
    lifecycle = data["weekly_lifecycle"]
    assert lifecycle["202608F3"]["lifecycle"] == "持續"
    assert lifecycle["202608F4"]["lifecycle"] == "首次觀測到"


def test_weekly_lifecycle_expired_vs_disappeared_unexplained(tmp_path):
    """昨天有、今天沒有：expiry<今天data_date → 依前次記錄推斷已到期；
    expiry>=今天data_date → 前次記錄後消失（原因不明）。用昨天存的
    contract_expiry_date判斷，不是今天list_weekly_contracts()的輸出
    （spec核心修正：4輪外審才收斂到這個規則）。"""
    (tmp_path / "oi_history.json").write_text(json.dumps({
        "2026-08-20": {
            "schema_version": 2, "session": "regular",
            "twchips_commit": "x", "pandas_version": "y",
            "near_month": {"contract_month": "202609", "call_wall": 24000,
                            "put_wall": 23000, "call_top3": [24000], "put_top3": [23000],
                            "distribution": {"call": {}, "put": {}}},
            "weekly": {
                "202608F3": {"status": "ok", "contract_expiry_date": "2026-08-20",  # 已過期
                              "call_wall": 24000, "put_wall": 23000,
                              "call_top3": [24000], "put_top3": [23000],
                              "distribution": {"call": {}, "put": {}}},
                "202609W1": {"status": "ok", "contract_expiry_date": "2026-09-02",  # 還沒到期
                              "call_wall": 500, "put_wall": 400,
                              "call_top3": [500], "put_top3": [400],
                              "distribution": {"call": {}, "put": {}}},
            },
        },
        "2026-08-21": {
            "schema_version": 2, "session": "regular",
            "twchips_commit": "x", "pandas_version": "y",
            "near_month": {"contract_month": "202609", "call_wall": 24100,
                            "put_wall": 23100, "call_top3": [24100], "put_top3": [23100],
                            "distribution": {"call": {}, "put": {}}},
            "weekly": {},  # 兩檔今天都不在了
        },
    }))
    (tmp_path / "fetch_log.jsonl").write_text(
        '{"fetch_id":"a","state":"ok","reason":null,"resolved_data_date":"2026-08-21"}\n'
    )
    data = build_dashboard_data(tmp_path)
    lifecycle = data["weekly_lifecycle"]
    assert lifecycle["202608F3"]["lifecycle"] == "依前次記錄推斷已到期"
    assert lifecycle["202609W1"]["lifecycle"] == "前次記錄後消失（原因不明）"


def test_weekly_lifecycle_error_status_still_classified_by_key_presence(tmp_path):
    """status=error的合約，key今天存在就照樣走「持續」分類，不會落到
    任何分類都套不進去的空隙（spec v5補上：ChatGPT第4輪抓到的缺口）。"""
    (tmp_path / "oi_history.json").write_text(json.dumps({
        "2026-08-20": {
            "schema_version": 2, "session": "regular",
            "twchips_commit": "x", "pandas_version": "y",
            "near_month": {"contract_month": "202609", "call_wall": 24000,
                            "put_wall": 23000, "call_top3": [24000], "put_top3": [23000],
                            "distribution": {"call": {}, "put": {}}},
            "weekly": {
                "202608F3": {"status": "ok", "contract_expiry_date": "2026-08-21",
                              "call_wall": 24000, "put_wall": 23000,
                              "call_top3": [24000], "put_top3": [23000],
                              "distribution": {"call": {}, "put": {}}},
            },
        },
        "2026-08-21": {
            "schema_version": 2, "session": "regular",
            "twchips_commit": "x", "pandas_version": "y",
            "near_month": {"contract_month": "202609", "call_wall": 24100,
                            "put_wall": 23100, "call_top3": [24100], "put_top3": [23100],
                            "distribution": {"call": {}, "put": {}}},
            "weekly": {
                "202608F3": {"status": "error", "contract_expiry_date": "2026-08-21",
                              "reason": "KeyError: simulated bug"},
            },
        },
    }))
    (tmp_path / "fetch_log.jsonl").write_text(
        '{"fetch_id":"a","state":"ok","reason":null,"resolved_data_date":"2026-08-21"}\n'
    )
    data = build_dashboard_data(tmp_path)
    lifecycle = data["weekly_lifecycle"]
    assert lifecycle["202608F3"]["lifecycle"] == "持續"
    assert lifecycle["202608F3"]["status"] == "error"


# --- Finding 1 修復：終端態（依前次記錄推斷已到期／前次記錄後消失（原因不明）
# 不能把昨天status="ok"複製過來，否則下游渲染會誤判走ok分支，印出
# Call —／Put —佔位符——這是每檔週選到期都會發生的常態，不是罕見異常。 ---

def test_weekly_lifecycle_terminal_entries_do_not_carry_status_ok():
    """_weekly_lifecycle()的終端分支不該把status=ok原封不動複製過來
    （這是bug的根本原因：下游渲染純粹依status=='ok'分派）。"""
    yesterday_weekly = {
        "202608F3": {
            "status": "ok", "contract_expiry_date": "2026-08-20",
            "call_wall": 24000, "put_wall": 23000,
            "call_top3": [24000], "put_top3": [23000],
        },
        "202609W1": {
            "status": "ok", "contract_expiry_date": "2026-09-02",
            "call_wall": 500, "put_wall": 400,
            "call_top3": [500], "put_top3": [400],
        },
    }
    result = _weekly_lifecycle({}, yesterday_weekly, "2026-08-21", "2026-08-20")
    assert result["202608F3"]["lifecycle"] == "依前次記錄推斷已到期"
    assert result["202609W1"]["lifecycle"] == "前次記錄後消失（原因不明）"
    for cm in ("202608F3", "202609W1"):
        assert result[cm].get("status") != "ok"


def test_render_weekly_row_terminal_lifecycle_has_no_placeholder():
    """兩個終端態各自單獨測render_weekly_row：不能印出Call —／Put —，
    要印出有意義的內容（lifecycle標籤本身）。"""
    for lifecycle in TERMINAL_LIFECYCLES:
        entry = {"contract_expiry_date": "2026-08-20", "lifecycle": lifecycle}
        html = _render_weekly_row("202608F3", entry)
        assert "Call —" not in html
        assert "Put —" not in html
        assert lifecycle in html  # 有意義的內容：標籤本身已經講清楚狀態


def test_render_html_terminal_lifecycle_no_call_put_placeholder(tmp_path):
    """端到端重現bug：兩檔週選昨天有、今天消失（一個已到期、一個消失
    不明），完整走build_dashboard_data→render_html，確認HTML實際渲染
    文字沒有Call —／Put —佔位符（Finding 1驗收標準）。"""
    (tmp_path / "oi_history.json").write_text(json.dumps({
        "2026-08-20": {
            "schema_version": 2, "session": "regular",
            "twchips_commit": "x", "pandas_version": "y",
            "near_month": {"contract_month": "202609", "call_wall": 24000,
                            "put_wall": 23000, "call_top3": [24000], "put_top3": [23000],
                            "distribution": {"call": {}, "put": {}}},
            "weekly": {
                "202608F3": {"status": "ok", "contract_expiry_date": "2026-08-20",  # 今天已過期
                              "call_wall": 24000, "put_wall": 23000,
                              "call_top3": [24000], "put_top3": [23000],
                              "distribution": {"call": {}, "put": {}}},
                "202609W1": {"status": "ok", "contract_expiry_date": "2026-09-02",  # 還沒到期就消失
                              "call_wall": 500, "put_wall": 400,
                              "call_top3": [500], "put_top3": [400],
                              "distribution": {"call": {}, "put": {}}},
            },
        },
        "2026-08-21": {
            "schema_version": 2, "session": "regular",
            "twchips_commit": "x", "pandas_version": "y",
            "near_month": {"contract_month": "202609", "call_wall": 24100,
                            "put_wall": 23100, "call_top3": [24100], "put_top3": [23100],
                            "distribution": {"call": {}, "put": {}}},
            "weekly": {},  # 兩檔今天都不在了
        },
    }))
    (tmp_path / "fetch_log.jsonl").write_text(
        '{"fetch_id":"a","state":"ok","reason":null,"resolved_data_date":"2026-08-21"}\n'
    )
    data = build_dashboard_data(tmp_path)
    lifecycle = data["weekly_lifecycle"]
    assert lifecycle["202608F3"]["lifecycle"] == "依前次記錄推斷已到期"
    assert lifecycle["202609W1"]["lifecycle"] == "前次記錄後消失（原因不明）"

    html = render_html(data)
    # near_month本身有真實top3資料（非空），所以html裡唯一可能出現
    # "Call —"／"Put —"的來源只會是週選終端態渲染錯誤（bug重現點）
    assert "Call —" not in html
    assert "Put —" not in html
    assert "依前次記錄推斷已到期" in html
    assert "前次記錄後消失（原因不明）" in html
