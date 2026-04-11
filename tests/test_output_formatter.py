from app.utils.output_formatter import draw_text_bar


def test_draw_text_bar():
    s = draw_text_bar("2连板", 9, 59, max_len=30)
    assert "2连板: 9" in s
    assert "█" in s
    assert "15.3%" in s or "15.2%" in s
