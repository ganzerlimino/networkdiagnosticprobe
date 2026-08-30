from ndp.ui.screens import shutdown_lines


def test_shutdown_lines() -> None:
    lines = shutdown_lines("Arresto in corso")
    assert lines[0] == "SPEGNIMENTO"
    assert "Arresto in corso" in lines
