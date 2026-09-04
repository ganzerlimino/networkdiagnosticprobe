from ndp.ui.layout import content_text_x, content_width, content_x_offset, draw_button_hints


def test_content_width_right_hint() -> None:
    assert content_width(320, "right", 28) == 292
    assert content_width(320, "bottom", 28) == 320


def test_content_width_left_hint() -> None:
    assert content_width(320, "left", 28) == 292


def test_content_width_none_hint() -> None:
    assert content_width(320, "none", 0) == 320
    assert content_x_offset("none", 0) == 0
    assert content_text_x("none", 0, 4) == 4


def test_content_x_offset_left_only() -> None:
    assert content_x_offset("left", 28) == 28
    assert content_x_offset("right", 28) == 0
    assert content_x_offset("bottom", 28) == 0


def test_content_text_x_gap() -> None:
    assert content_text_x("left", 28, 0) == 28
    assert content_text_x("left", 28, 4) == 32
    assert content_text_x("right", 28, 4) == 4


def test_hint_y_positions_offset() -> None:
    from ndp.ui.layout import hint_y_positions

    top, mid, bottom = hint_y_positions(240, 24)
    assert top == 76
    assert mid == 134
    assert bottom == 192
