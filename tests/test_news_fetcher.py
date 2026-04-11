from app.services.news_fetcher import filter_news, relevance_scoring


def test_relevance_market_terms():
    s = (
        "A股沪深两市放量上涨，证监会就交易监管征求意见，"
        "新能源板块多股涨停，北向资金净流入"
    )
    assert relevance_scoring(s) > 0.6


def test_relevance_noise_penalty():
    s = "华融领和德黑兰举行会谈"
    assert relevance_scoring(s) < 0.6


def test_filter_news_cap():
    rows = [
        {"tag": "宏观", "summary": "某邻国领导人访问讨论农业合作"},
        {
            "tag": "市场",
            "summary": (
                "A股股市放量上攻，沪深北向资金净流入，沪指深成指走强，"
                "证券板块领涨涨停家数上升"
            ),
        },
    ]
    out = filter_news(rows, min_score=0.6, max_items=3)
    assert len(out) == 1
    assert "沪深" in out[0]["summary"]
