"""replay_task 摘要行补全逻辑。"""
from app.services.replay_task import _ensure_summary_line


def test_ensure_summary_keeps_existing():
    t = "【摘要】市场阶段：强势｜适宜度：高｜置信度：中\n\n正文"
    assert _ensure_summary_line(t) == t


def test_ensure_summary_prepends_when_missing():
    t = "正文第一段\n第二段"
    out = _ensure_summary_line(t)
    assert out.startswith("【摘要】")
    assert "正文第一段" in out


def test_ensure_summary_empty_unchanged():
    assert _ensure_summary_line("") == ""
    assert _ensure_summary_line("   ") == "   "
