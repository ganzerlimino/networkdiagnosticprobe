#!/usr/bin/env bash
# Release wlan0 from NetworkManager / wpa_supplicant before NDP hotspot starts.
set -euo pipefail

IFACE="${NDP_WIFI_IFACE:-wlan0}"

if command -v rfkill >/dev/null 2>&1; then
  rfkill unblock all 2>/dev/null || true
  rfkill unblock wifi 2>/dev/null || true
fi

for svc in "wpa_supplicant@${IFACE}.service" wpa_supplicant.service dhcpcd@"${IFACE}.service"; do
  systemctl stop "$svc" 2>/dev/null || true
done

if command -v nmcli >/dev/null 2>&1; then
  nmcli device set "$IFACE" managed no 2>/dev/null || true
fi

exit 0
