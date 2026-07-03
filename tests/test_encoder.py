from ndp.ui.encoder import EncoderMapping, QuadratureDecoder, RotaryEncoder


def test_quadrature_one_detent_clockwise() -> None:
    decoder = QuadratureDecoder(steps_per_detent=4)
    # Gray-code CW cycle: 00 -> 10 -> 11 -> 01 -> 00
    sequence = [(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]
    cw_total = 0
    ccw_total = 0
    for clk, dt in sequence[1:]:
        cw, ccw = decoder.update(clk, dt)
        cw_total += cw
        ccw_total += ccw
    assert cw_total == 1
    assert ccw_total == 0


def test_quadrature_one_detent_counter_clockwise() -> None:
    decoder = QuadratureDecoder(steps_per_detent=4)
    sequence = [(0, 0), (0, 1), (1, 1), (1, 0), (0, 0)]
    cw_total = 0
    ccw_total = 0
    for clk, dt in sequence[1:]:
        cw, ccw = decoder.update(clk, dt)
        cw_total += cw
        ccw_total += ccw
    assert cw_total == 0
    assert ccw_total == 1


def test_quadrature_ignores_bounce() -> None:
    decoder = QuadratureDecoder(steps_per_detent=4)
    cw, ccw = decoder.update(0, 0)
    assert (cw, ccw) == (0, 0)
    cw, ccw = decoder.update(0, 0)
    assert (cw, ccw) == (0, 0)


def test_encoder_mapping_defaults() -> None:
    mapping = EncoderMapping()
    assert mapping.clk == 17
    assert mapping.dt == 27
    assert mapping.sw == 22


def test_create_ui_input_encoder() -> None:
    from ndp.core.config import NdpConfig
    from ndp.ui.encoder import RotaryEncoder
    from ndp.ui.input import create_ui_input

    config = NdpConfig(ui_input="encoder")
    device = create_ui_input(config)
    assert isinstance(device, RotaryEncoder)


def test_create_ui_input_buttons() -> None:
    from ndp.core.config import NdpConfig
    from ndp.ui.buttons import PhysicalButtons
    from ndp.ui.input import create_ui_input

    config = NdpConfig(ui_input="buttons")
    device = create_ui_input(config)
    assert isinstance(device, PhysicalButtons)


def test_config_encoder_defaults() -> None:
    from ndp.core.config import NdpConfig

    config = NdpConfig.from_mapping({"ui": {"input": "encoder"}})
    assert config.ui_hint_edge == "none"
    assert config.ui_content_margin_side == 0
    assert config.ui_encoder_clk == 17
    assert config.ui_encoder_dt == 27
    assert config.ui_encoder_sw == 22
