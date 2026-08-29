from ndp.web.config_schema import (
    coerce_field_value,
    config_sections,
    get_nested_value,
    set_nested_value,
)


def test_config_sections_include_hotspot_password() -> None:
    sections = config_sections()
    hotspot = next(section for section in sections if section["id"] == "hotspot")
    keys = {field["key"] for field in hotspot["fields"]}  # type: ignore[index]
    assert "wifi_hotspot.password" in keys


def test_nested_get_set() -> None:
    data: dict = {}
    set_nested_value(data, "wifi_hotspot.password", "ndp-probe")
    assert get_nested_value(data, "wifi_hotspot.password") == "ndp-probe"


def test_coerce_bool() -> None:
    assert coerce_field_value("bool", "true") is True
    assert coerce_field_value("bool", "false") is False
