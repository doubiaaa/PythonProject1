# -*- coding: utf-8 -*-
from app.services.report_builder import (
    _detect_stage_92kebi,
    append_core_stocks_and_plan_if_missing,
    enforce_final_report_cleanup,
    enforce_execution_review_block,
    enforce_market_env_block,
    missing_core_stocks_and_plan,
    sanitize_replay_report_output,
    sanitize_replay_report_output_with_stats,
)


def test_missing_detection():
    a = "## 数据快照\nxx\n## 情绪与周期\nxx\n## 主线与备选\nxx\n## 附录/心法\nyy"
    assert missing_core_stocks_and_plan(a) == (False, False)
    b = "### 一、盘面\n"
    assert missing_core_stocks_and_plan(b) == (True, True)


def test_append_inserts_five_and_seven():
    class _F:
        _last_market_phase = "混沌·试错期"
        _last_position_suggestion = "15-25%"
        _last_auction_meta = {
            "top_pool": [{"code": "000001", "name": "测试", "tag": "龙头", "lb": 2, "sector": "银", "score": 8.1}],
            "main_sectors": ["银行"],
        }
        _last_dragon_trader_meta = {}
        _last_zt_pool = None

    raw = "# 标题\n### 免责声明\n> xx\n"
    out = append_core_stocks_and_plan_if_missing(
        raw,
        actual_date="20260408",
        data_fetcher=_F(),
        enable=True,
        use_llm=False,
    )
    assert "## 数据快照" in out
    assert "## 情绪与周期" in out
    assert "## 主线与备选" in out
    assert "主线板块评估（多维评分）" in out
    assert "板块RPS(20日)" in out
    assert "## 附录/心法" in out
    assert "若以下条件任一不满足，则当日开仓 0%" in out
    assert "### 免责声明" in out


def test_sanitize_adds_position_conflict_table():
    raw = "计划A：程序仓位 15-30%\n计划B：满仓（100%）\n"
    out = sanitize_replay_report_output(raw)
    assert "仓位来源" in out
    assert "执行优先级" in out


def test_sanitize_compresses_wide_table():
    raw = (
        "| field1 | field2 | field3 | field4 |\n"
        "|---|---|---|---|\n"
        "| this_is_a_very_long_cell_content_exceeding_eighty_characters_for_mobile_layout_check | b | c | d |\n"
    )
    out = sanitize_replay_report_output(raw)
    assert "自动转列表" in out
    assert "| field1" not in out


def test_sanitize_stats_are_reported():
    raw = (
        "结论：可交易\n"
        "计划A：程序仓位 10-20%\n"
        "计划B：满仓（100%）\n"
        "## 附录/心法\n"
        "- 1\n- 2\n- 3\n- 4\n- 5\n- 6\n- 7\n- 8\n- 9\n- 10\n- 11\n"
    )
    _, stats = sanitize_replay_report_output_with_stats(raw)
    assert stats["status_replacements"] >= 1
    assert stats["position_conflicts"] == 1
    assert stats["appendix_lines_trimmed"] >= 1


def test_sanitize_quantifies_subjective_triggers():
    raw = "触发1：分时重心上移；触发2：放量确认；触发3：快速突破近期平台。"
    out, stats = sanitize_replay_report_output_with_stats(raw)
    assert "开盘后15分钟内" in out
    assert "前5分钟成交额 >=" in out
    assert "价格突破过去5日最高价" in out
    assert stats["trigger_replacements"] >= 3


def test_enforce_market_env_block_inserts_before_section_and_marks_summary():
    class _F:
        _last_market_env_snapshot = {
            "sh_point": 3150.12,
            "sh_pct": 0.8,
            "sh_ma20_position": "上",
            "sh_ma20_direction": "上",
            "turnover_yi": None,
            "turnover_change_pct": None,
            "turnover_gt_8000": None,
            "up_count": 3200,
            "down_count": 1800,
            "rise_fall_ratio": 1.78,
            "yest_limitup_index_pct": 1.2,
            "yest_limitup_gt_2pct": False,
            "has_missing": True,
        }
        _last_email_kpi = {}

    raw = "【摘要】大盘：⚠️ 观望\n\n### 一、大盘与主线环境评估\n正文"
    out, stats = enforce_market_env_block(raw, _F())
    assert "### 程序侧行情接口快照（系统性风险评估）" in out
    assert out.index("程序侧行情接口快照") < out.index("### 一、大盘与主线环境评估")
    assert "数据缺失，系统性风险评估不完整" in out
    assert stats["market_env_block_inserted"] == 1
    assert stats["summary_missing_marked"] == 1


def test_sector_rps_missing_shows_no_data():
    class _F:
        _last_market_phase = "高位震荡"
        _last_position_suggestion = "20-30%"
        _last_market_env_snapshot = {"turnover_yi": 10000.0}
        _last_email_kpi = {"turnover_yi_est": 10000.0}
        _last_sector_rank_df = None
        _last_auction_meta = {
            "main_sectors": ["算力"],
            "top_pool": [
                {"code": "000001", "name": "A", "sector": "算力", "amount_yi": 6.2},
                {"code": "000002", "name": "B", "sector": "算力", "amount_yi": 5.1},
            ],
        }
        _last_dragon_trader_meta = {}

    out = append_core_stocks_and_plan_if_missing(
        "# t\n### 免责声明\nx",
        actual_date="20260421",
        data_fetcher=_F(),
        enable=True,
        use_llm=False,
    )
    assert "主线板块评估（多维评分）" in out
    assert "无数据" in out


def test_enforce_execution_review_block_before_section_five():
    class _F:
        _last_auction_meta = {
            "top_pool": [
                {"code": "000001", "name": "平安银行"},
                {"code": "000002", "name": "万科A"},
            ]
        }

    raw = "## 明日计划\n内容\n\n### 五、持仓标的的应对预案\n内容"
    out, stats = enforce_execution_review_block(raw, _F())
    assert "## 昨日计划执行评价" in out
    assert "000001 平安银行" in out
    assert out.index("## 昨日计划执行评价") < out.index("### 五、持仓标的的应对预案")
    assert stats["execution_review_inserted"] == 1


def test_final_cleanup_rules():
    raw = (
        "龙头战法复盘\n交易日 2026-04-21\n"
        "### 五、核心股票焦\n### 五、核心股票焦\n"
        "| a ｜ b |\n|---|---|\n| 1 | 2 |\n"
        "收益 12.3 % 乱码🙂\n"
    )
    out, stats = enforce_final_report_cleanup(raw, "20260421")
    assert "交易日 20260421" in out
    assert "12.3%" in out
    assert "🙂" not in out
    assert out.count("### 五、核心股票焦") == 1
    assert stats["title_date_normalized"] >= 1


def test_detect_stage_92kebi_main_rise():
    stage, advice = _detect_stage_92kebi(
        max_lb=6,
        premium_pct=3.5,
        zhaban_rate_pct=20.0,
        dt_count=3,
        mid_fall_limit=False,
        has_new_theme_first_board=False,
    )
    assert stage == "主升"
    assert "聚焦龙头" in advice


def test_detect_stage_92kebi_main_fall():
    stage, advice = _detect_stage_92kebi(
        max_lb=2,
        premium_pct=-1.2,
        zhaban_rate_pct=30.0,
        dt_count=20,
        mid_fall_limit=True,
        has_new_theme_first_board=False,
    )
    assert stage == "主跌"
    assert "空仓" in advice
