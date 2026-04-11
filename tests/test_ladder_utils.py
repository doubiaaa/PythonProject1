# -*- coding: utf-8 -*-
from app.utils.ladder_utils import (
    display_max_lb_row,
    ladder_level_count,
    max_lb_from_ladder_dict,
)


def test_ladder_level_count_string_keys():
    lad = {"2": 3, "3": 1, 4: 2}
    assert ladder_level_count(lad, 2) == 3
    assert ladder_level_count(lad, 3) == 1
    assert ladder_level_count(lad, 4) == 2


def test_max_lb_from_ladder_dict():
    assert max_lb_from_ladder_dict({"1": 10, "5": 2}) == 5
    assert max_lb_from_ladder_dict({}) == 0


def test_display_max_lb_row_fallback():
    assert display_max_lb_row({"max_lb": 0, "ladder": {"3": 2, "1": 5}}) == 3
    assert display_max_lb_row({"max_lb": 4, "ladder": {}}) == 4
