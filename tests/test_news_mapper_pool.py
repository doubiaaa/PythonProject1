# -*- coding: utf-8 -*-
from app.services.news_mapper import format_pool_news_hits_markdown


def test_pool_news_hit_by_code():
    s = format_pool_news_hits_markdown(
        ["无关消息", "机构增持 600519 白酒龙头"],
        [{"code": "600519", "name": "贵州茅台"}],
    )
    assert "命中" in s
    assert "600519" in s


def test_pool_news_hit_by_name():
    s = format_pool_news_hits_markdown(
        ["贵州茅台发布业绩预告"],
        [{"code": "600519", "name": "贵州茅台"}],
    )
    assert "贵州茅台" in s
