from ndp.ui.layout import content_width, content_x_offset, draw_button_hints


def test_content_width_right_hint() -> None:
    assert content_width(320, "right", 48) == 272
    assert content_width(320, "bottom", 48) == 320


def test_content_width_left_hint() -> None:
    assert content_width(320, "left", 40) == 280


def test_content_x_offset_left_only() -> None:
    assert content_x_offset("left", 48) == 48
    assert content_x_offset("right", 48) == 0
    assert content_x_offset("bottom", 48) == 0
