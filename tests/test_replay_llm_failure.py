# -*- coding: utf-8 -*-
from app.services.replay_task import (
    _is_llm_failure_payload,
    _ensure_summary_line,
    _ensure_dragon_report_sections,
)


def test_is_llm_failure_429():
    body = 'API请求失败（429）：{"error": {"code":"1302","message":"限速"}}'
    assert _is_llm_failure_payload(body)


def test_is_llm_failure_false_for_normal():
    assert not _is_llm_failure_payload("### 一、盘面综述\n你好")


def test_summary_line_api_error_not_model_fallback():
    err = 'API请求失败（429）：{"error": {"code":"1302"}}'
    out = _ensure_summary_line(err, market_phase="高位震荡期")
    assert out.startswith("【摘要】")
    assert "未生成正文" in out
    assert "模型未输出规范首行" not in out


def test_dragon_sections_api_error_note():
    err = "API请求失败（429）：x"
    out = _ensure_dragon_report_sections(_ensure_summary_line(err))
    assert "未生成 AI 复盘长文" in out
    assert "未检测到以下章节标题" not in out
