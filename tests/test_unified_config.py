# -*- coding: utf-8 -*-

from app.infrastructure.unified_config import (
    apply_strategy_profile_overlay,
    build_effective_config,
    deep_merge,
)


def test_deep_merge_nested():
    a = {"data_source": {"timeout": 8, "retry_times": 3}, "w_main": 0.2}
    b = {"data_source": {"timeout": 12}}
    m = deep_merge(a, b)
    assert m["data_source"]["timeout"] == 12
    assert m["data_source"]["retry_times"] == 3
    assert m["w_main"] == 0.2


def test_profile_overlay_after_user_selects_name(tmp_path, monkeypatch):
    monkeypatch.delenv("REPLAY_CONFIG_FILE", raising=False)
    cfg_path = tmp_path / "rc.json"
    cfg_path.write_text(
        '{"active_strategy_profile": "aggressive", "strategy_profiles": {'
        '"default": {}, "aggressive": {"w_main": 0.99}}}',
        encoding="utf-8",
    )
    defaults = {
        "w_main": 0.22,
        "active_strategy_profile": "default",
        "strategy_profiles": {"default": {}, "aggressive": {"w_main": 0.99}},
    }
    eff = build_effective_config(
        defaults=defaults,
        config_file=str(cfg_path),
        project_root=str(tmp_path),
    )
    assert eff["w_main"] == 0.99


def test_env_flat_overrides(monkeypatch):
    monkeypatch.setenv("LLM_RETRY_ATTEMPTS", "5")
    defaults = {"llm_retry_attempts": 3}
    eff = build_effective_config(
        defaults=defaults,
        config_file="/nonexistent/replay_config.json",
        project_root="/tmp",
    )
    assert eff["llm_retry_attempts"] == 5


def test_apply_strategy_profile_skips_metadata_keys():
    cfg = {
        "w_main": 0.1,
        "active_strategy_profile": "p",
        "strategy_profiles": {
            "p": {
                "w_main": 0.5,
                "strategy_profiles": {"should": "not_apply"},
            }
        },
    }
    out = apply_strategy_profile_overlay(cfg)
    assert out["w_main"] == 0.5
    assert "should" not in (out.get("strategy_profiles") or {}).get("p", {})


def test_replay_nested_env(monkeypatch):
    monkeypatch.setenv("REPLAY__data_source__timeout", "99")
    defaults = {"data_source": {"timeout": 8, "retry_times": 1}}
    eff = build_effective_config(
        defaults=defaults,
        config_file="/nonexistent/replay_config.json",
        project_root="/tmp",
    )
    assert eff["data_source"]["timeout"] == 99
