from ndp.locale.loader import (
    list_locales,
    load_locale,
    load_themes_catalog,
    resolve_theme_id,
    tft_palette,
    translate,
    translate_config_field,
)


def test_list_locales_includes_it_and_en() -> None:
    codes = {entry["code"] for entry in list_locales()}
    assert "it" in codes
    assert "en" in codes


def test_load_locale_merges_fallback() -> None:
    locale = load_locale("it")
    assert locale["nav"]["monitor"] == "Monitor"
    assert locale["nav"]["plant"] == "Impianto"
    assert translate(locale, "plant.scan") == "Scansiona impianto"


def test_load_themes_catalog_has_default_theme() -> None:
    catalog = load_themes_catalog()
    default = resolve_theme_id(None)
    assert default in catalog["themes"]
    palette = tft_palette(default)
    assert "bg" in palette
    assert len(palette["bg"]) == 3


def test_list_locales_includes_de() -> None:
    codes = {entry["code"] for entry in list_locales()}
    assert "de" in codes


def test_load_locale_de_has_plant_title() -> None:
    locale = load_locale("de")
    assert locale["nav"]["plant"] == "Anlage"


def test_translate_config_field_dotted_key() -> None:
    locale = load_locale("de")
    label = translate_config_field(locale, "ui.theme", "label", fallback="Theme")
    assert label == "Farbschema"
    assert "config.fields" not in label


