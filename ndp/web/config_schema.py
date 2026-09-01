"""Web form schema for NDP configuration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ConfigField:
    key: str
    label: str
    help: str
    field_type: str  # string | int | float | bool | select | text
    options: tuple[str, ...] = ()
    section: str = "general"


def config_sections(locale_code: str = "it") -> list[dict[str, object]]:
    from ndp.locale.loader import list_locales, load_locale, translate

    locale = load_locale(locale_code)
    locale_options = tuple(entry["code"] for entry in list_locales())
    fields = _config_fields(locale_options)
    sections: dict[str, dict[str, object]] = {}
    for field in fields:
        section = sections.setdefault(
            field.section,
            {
                "id": field.section,
                "title": translate(locale, f"config.sections.{field.section}") or _section_title(field.section),
                "fields": [],
            },
        )
        label = translate(locale, f"config.fields.{field.key}.label") or field.label
        help_text = translate(locale, f"config.fields.{field.key}.help") or field.help
        section["fields"].append(
            {
                "key": field.key,
                "label": label,
                "help": help_text,
                "type": field.field_type,
                "options": list(field.options),
            }
        )
    return list(sections.values())


def _section_title(section_id: str) -> str:
    return {
        "network": "Rete probe",
        "ui": "Display TFT",
        "web": "Web UI",
        "hotspot": "Hotspot telefono",
        "ping": "Ping",
        "discovery": "Discover",
        "appearance": "Aspetto",
        "logging": "Log",
        "console": "Console",
    }.get(section_id, section_id)


def _config_fields(locale_options: tuple[str, ...]) -> tuple[ConfigField, ...]:
    locales = locale_options or ("it", "en", "de")
    return (
        ConfigField("interface", "Interfaccia monitorata", "Di solito eth0 (cavo diagnostica).", "string", section="network"),
        ConfigField("poll_interval_link_up", "Polling link UP (s)", "Aggiornamento quando il cavo è collegato.", "float", section="network"),
        ConfigField("poll_interval_link_down", "Polling link DOWN (s)", "Aggiornamento quando il cavo è scollegato.", "float", section="network"),
        ConfigField("lldp.cache_ttl_seconds", "Cache LLDP (s)", "Validità dati LLDP/CDP.", "int", section="network"),
        ConfigField("ui.enabled", "Display TFT attivo", "Rotazione automatica schermate sul display.", "bool", section="ui"),
        ConfigField("ui.framebuffer", "Framebuffer", "Device Linux del TFT (es. /dev/fb1).", "string", section="ui"),
        ConfigField("ui.auto_cycle_seconds", "Rotazione schermate (s)", "0 = disabilitata.", "float", section="ui"),
        ConfigField("ui.input", "Input locale", "none = solo telefono.", "select", ("none", "buttons", "encoder"), section="ui"),
        ConfigField("ui.hint_edge", "Bordo icone tasti", "none consigliato con input none.", "select", ("none", "left", "right", "bottom"), section="ui"),
        ConfigField("ui.backlight_enabled", "Retroilluminazione", "Accende GPIO backlight all'avvio.", "bool", section="ui"),
        ConfigField("web.enabled", "Web UI attiva", "Interfaccia mobile su porta HTTP.", "bool", section="web"),
        ConfigField("web.host", "Host ascolto", "0.0.0.0 = tutte le interfacce.", "string", section="web"),
        ConfigField("web.port", "Porta HTTP", "Default 8080.", "int", section="web"),
        ConfigField("wifi_hotspot.enabled", "Hotspot attivo", "Crea rete NDP-XXXX per il telefono.", "bool", section="hotspot"),
        ConfigField("wifi_hotspot.ssid_prefix", "Prefisso SSID", "Suffisso = ultime 4 cifre MAC Wi-Fi.", "string", section="hotspot"),
        ConfigField("wifi_hotspot.password", "Password WPA2", "Minimo 8 caratteri. Vuoto = rete aperta (sconsigliato).", "string", section="hotspot"),
        ConfigField("wifi_hotspot.interface", "Interfaccia Wi-Fi", "Di solito wlan0.", "string", section="hotspot"),
        ConfigField("wifi_hotspot.ip", "IP hotspot", "URL telefono: http://<ip>:8080/", "string", section="hotspot"),
        ConfigField("wifi_hotspot.channel", "Canale Wi-Fi", "Canale 2.4 GHz (es. 6).", "int", section="hotspot"),
        ConfigField("wifi_hotspot.country", "Paese regolatorio", "Codice ISO (es. IT).", "string", section="hotspot"),
        ConfigField("ping.count", "Pacchetti ICMP", "Numero ping per destinazione.", "int", section="ping"),
        ConfigField("ping.timeout_seconds", "Timeout ping (s)", "Timeout per host.", "float", section="ping"),
        ConfigField("ping.packet_size", "Dimensione pacchetto (byte)", "Payload ICMP (-s). Default 56.", "int", section="ping"),
        ConfigField("discovery.disconnect_wait_seconds", "Attesa scollegamento (s)", "Wizard Discover Up/Down.", "float", section="discovery"),
        ConfigField("discovery.flush_arp_before_second_scan", "Flush ARP", "Svuota cache prima della 2ª scansione.", "bool", section="discovery"),
        ConfigField("discovery.verify_replug", "Verifica ricollegamento", "Passo finale wizard Up/Down.", "bool", section="discovery"),
        ConfigField("discovery.mndp_listen_seconds", "Ascolto MNDP (s)", "Durata probe MNDP per status e tab MikroTik.", "float", section="discovery"),
        ConfigField("discovery.passive_listen_seconds", "Sniff passivo default (s)", "Durata predefinita tab Passive check.", "float", section="discovery"),
        ConfigField("discovery.scenario", "Profilo scenario", "Preset timeout discovery (impianto/retail/ufficio).", "select", ("impianto", "retail", "ufficio"), section="discovery"),
        ConfigField("ui.locale", "Lingua interfaccia", "Scegli la lingua e salva.", "select", locales, section="appearance"),
        ConfigField("ui.theme", "Tema colori", "Web UI e display TFT (riavvia ndp per TFT).", "select", ("field-dark", "industrial-amber", "high-contrast", "office-light", "night-vision"), section="appearance"),
        ConfigField("logging.level", "Livello log", "DEBUG, INFO, WARNING, ERROR.", "select", ("DEBUG", "INFO", "WARNING", "ERROR"), section="logging"),
        ConfigField("console.enabled", "Output console", "Riepilogo periodico su journal.", "bool", section="console"),
        ConfigField("console.refresh_seconds", "Refresh console (s)", "Intervallo stampa console.", "float", section="console"),
    )


def get_nested_value(data: dict[str, Any], path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def set_nested_value(data: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    current = data
    for part in parts[:-1]:
        node = current.setdefault(part, {})
        if not isinstance(node, dict):
            raise ValueError(f"percorso config non valido: {path}")
        current = node
    current[parts[-1]] = value


def coerce_field_value(field_type: str, raw: Any) -> Any:
    if field_type == "bool":
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            return raw.strip().lower() in {"1", "true", "yes", "on", "si", "sì"}
        return bool(raw)
    if field_type == "int":
        return int(raw)
    if field_type == "float":
        return float(raw)
    if field_type == "text":
        return str(raw)
    return str(raw).strip()
