"""策略归因：按标签分组统计。"""
from app.services.weekly_performance import SignalReturnRow, build_attribution_markdown


def test_attribution_by_tag():
    rows = [
        SignalReturnRow(
            "20260101",
            "600000",
            "A",
            1,
            "20260102",
            "20260103",
            2.0,
            "ok",
            tag="人气龙头",
            sector="银行",
        ),
        SignalReturnRow(
            "20260101",
            "000001",
            "B",
            2,
            "20260102",
            "20260103",
            -1.0,
            "ok",
            tag="人气龙头",
            sector="地产",
        ),
    ]
    md = build_attribution_markdown(rows)
    assert "人气龙头" in md
    assert "0.5%" in md or "0.5" in md
