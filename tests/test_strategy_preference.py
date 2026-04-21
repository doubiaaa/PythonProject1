"""策略偏好：标签映射与权重平滑。"""
from app.services.strategy_preference import (
    BUCKETS,
    _apply_floor_cap,
    _clip_bucket_normalize,
    _limit_weight_delta_vs_old,
    _smooth,
    _suggested_weights_from_rows,
    tag_to_bucket,
)

from app.services.weekly_performance import SignalReturnRow

_OLD = {k: 0.2 for k in BUCKETS}


def test_tag_to_bucket():
    assert tag_to_bucket("人气龙头") == "龙头"
    assert tag_to_bucket("活口核心") == "低吸"
    assert tag_to_bucket("趋势中军") == "趋势"


def test_suggested_weights():
    rows = [
        SignalReturnRow(
            "20260101",
            "600000",
            "A",
            1,
            "20260102",
            "20260103",
            10.0,
            "ok",
            tag="人气龙头",
        ),
        SignalReturnRow(
            "20260101",
            "000001",
            "B",
            2,
            "20260102",
            "20260103",
            -5.0,
            "ok",
            tag="活口核心",
        ),
    ]
    w, _counts = _suggested_weights_from_rows(
        rows, _OLD, min_trades_per_style=1
    )
    assert abs(sum(w[k] for k in BUCKETS) - 1.0) < 0.01
    assert w["龙头"] != w["低吸"]


def test_smooth_and_cap():
    old = {k: 0.2 for k in BUCKETS}
    new = {k: 0.2 for k in BUCKETS}
    new["龙头"] = 0.5
    m = _smooth(old, new, 0.3)
    assert abs(sum(m.values()) - 1.0) < 0.01
    c = _apply_floor_cap(m, max_single=0.55, min_each=0.08)
    assert all(0.08 <= c[k] <= 0.55 for k in BUCKETS)


def test_clip_bucket_normalize():
    w = {k: 0.2 for k in BUCKETS}
    w["龙头"] = 0.95
    w["低吸"] = 0.02
    c = _clip_bucket_normalize(w, 0.01, 0.99)
    assert abs(sum(c.values()) - 1.0) < 0.001
    assert all(0.01 <= c[k] <= 0.99 for k in BUCKETS)


def test_limit_weight_delta():
    old = {k: 0.2 for k in BUCKETS}
    new = {k: 0.2 for k in BUCKETS}
    new["龙头"] = 0.6
    out = _limit_weight_delta_vs_old(new, old, max_delta=0.10)
    assert abs(out["龙头"] - old["龙头"]) <= 0.11
    assert abs(sum(out.values()) - 1.0) < 0.01
