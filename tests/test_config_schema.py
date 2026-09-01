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


def test_config_sections_include_appearance() -> None:
    sections = config_sections()
    appearance = next(section for section in sections if section["id"] == "appearance")
    keys = {field["key"] for field in appearance["fields"]}  # type: ignore[index]
    assert "ui.locale" in keys
    assert "ui.theme" in keys


def test_config_sections_german_labels() -> None:
    sections = config_sections("de")
    appearance = next(section for section in sections if section["id"] == "appearance")
    theme = next(field for field in appearance["fields"] if field["key"] == "ui.theme")  # type: ignore[index]
    assert theme["label"] == "Farbschema"
    assert "config.fields" not in str(theme["label"])


def test_nested_get_set() -> None:
    data: dict = {}
    set_nested_value(data, "wifi_hotspot.password", "ndp-probe")
    assert get_nested_value(data, "wifi_hotspot.password") == "ndp-probe"


def test_coerce_bool() -> None:
    assert coerce_field_value("bool", "true") is True
    assert coerce_field_value("bool", "false") is False
