from app.output.replay_email_subject import build_replay_success_email_subject


def test_success_subject_appends_rule_status_suffix():
    subj = build_replay_success_email_subject(
        summary_line="【摘要】大盘：可交易｜主线：AI",
        trade_date="20260421",
        mode_name="次日竞价半路模式",
        rule_status_suffix="[可执行2/阻塞1]",
    )
    assert "[可执行2/阻塞1]" in subj
    assert subj.endswith("· 20260421")


def test_success_subject_without_summary_uses_default_title_and_suffix():
    subj = build_replay_success_email_subject(
        summary_line="",
        trade_date="20260421",
        mode_name="次日竞价半路模式",
        rule_status_suffix="[可执行0/阻塞3]",
    )
    assert "复盘完成" in subj
    assert "[可执行0/阻塞3]" in subj

