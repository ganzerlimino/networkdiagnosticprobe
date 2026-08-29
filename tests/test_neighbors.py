from ndp.core.collectors.neighbors import _pick_primary
from ndp.core.state import NeighborState


def test_pick_primary_prefers_lldp_over_mndp() -> None:
    lldp = NeighborState(protocol="LLDP", available=True, switch_name="sw1")
    mndp = NeighborState(protocol="MNDP", available=True, switch_name="mt1")
    primary = _pick_primary([mndp, lldp])
    assert primary.protocol == "LLDP"


def test_pick_primary_uses_mndp_when_lldp_missing() -> None:
    mndp = NeighborState(protocol="MNDP", available=True, switch_name="mt1")
    lldp = NeighborState(protocol="LLDP", available=False, message="no data")
    primary = _pick_primary([lldp, mndp])
    assert primary.protocol == "MNDP"
