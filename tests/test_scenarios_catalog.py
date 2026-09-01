from ndp.scenarios.catalog import get_scenario, list_scenarios, scenario_timeouts


def test_list_scenarios_includes_impianto() -> None:
    rows = list_scenarios()
    ids = {row["id"] for row in rows}
    assert "impianto" in ids
    assert any(row["default"] for row in rows if row["id"] == "impianto")


def test_get_scenario_returns_timeouts() -> None:
    scenario = get_scenario("retail")
    assert scenario["id"] == "retail"
    assert scenario["printer_timeout_seconds"] == 6
    assert scenario["include_port_profile"] is False


def test_scenario_timeouts_unknown_falls_back_to_default() -> None:
    timeouts = scenario_timeouts("unknown-profile")
    assert timeouts["industrial_timeout_seconds"] == 4
