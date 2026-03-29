"""财经要闻关键词匹配（不访问外网）。"""
from app.services.data_fetcher import (
    _news_keywords_from_meta,
    _news_row_matches,
)


def test_keywords_from_meta():
    meta = {
        "top_pool": [
            {"code": "600519", "name": "贵州茅台"},
        ],
        "main_sectors": ["白酒", "消费"],
    }
    codes, names = _news_keywords_from_meta(meta)
    assert "600519" in codes
    assert any("茅台" in n for n in names)


def test_row_matches_code():
    ok, hint = _news_row_matches(
        "600519 发布业绩预告，净利润同比大增",
        {"600519"},
        [],
    )
    assert ok is True
    assert "600519" in hint


def test_row_matches_name():
    ok, hint = _news_row_matches(
        "白酒板块午后走强，贵州茅台领涨",
        set(),
        ["贵州茅台", "茅台"],
    )
    assert ok is True
    assert "茅台" in hint or "贵州茅台" in hint
