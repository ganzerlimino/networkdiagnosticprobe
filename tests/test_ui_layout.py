from ndp.ui.layout import content_width, draw_button_hints


def test_content_width_right_hint() -> None:
    assert content_width(320, "right", 48) == 272
    assert content_width(320, "bottom", 48) == 320


def test_content_width_left_hint() -> None:
    assert content_width(320, "left", 40) == 280
