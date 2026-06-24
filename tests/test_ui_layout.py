from ndp.ui.layout import content_text_x, content_width, content_x_offset, draw_button_hints


def test_content_width_right_hint() -> None:
    assert content_width(320, "right", 32) == 288
    assert content_width(320, "bottom", 32) == 320


def test_content_width_left_hint() -> None:
    assert content_width(320, "left", 32) == 288


def test_content_x_offset_left_only() -> None:
    assert content_x_offset("left", 32) == 32
    assert content_x_offset("right", 32) == 0
    assert content_x_offset("bottom", 32) == 0


def test_content_text_x_gap() -> None:
    assert content_text_x("left", 32, 4) == 36
    assert content_text_x("left", 32, 0) == 32
    assert content_text_x("right", 32, 4) == 4


def test_hint_y_positions_offset() -> None:
    from ndp.ui.layout import hint_y_positions

    top, mid, bottom = hint_y_positions(240, 24)
    assert top == 76
    assert mid == 134
    assert bottom == 192
