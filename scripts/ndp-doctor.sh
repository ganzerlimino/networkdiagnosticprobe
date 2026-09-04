#!/usr/bin/env bash
# Quick health check when NDP display / hotspot do not start.
set -u

NDP_ROOT="${NDP_ROOT:-/opt/ndp}"
CONFIG="${NDP_CONFIG_DIR:-/etc/ndp}/config.yaml"
LOCALE_DIR="${NDP_CONFIG_DIR:-/etc/ndp}/locale"

section() { echo; echo "=== $1 ==="; }

section "NDP services"
for svc in ndp-hotspot ndp lldpd; do
  if systemctl is-active --quiet "$svc" 2>/dev/null; then
    echo "OK  $svc: active"
  elif systemctl is-enabled --quiet "$svc" 2>/dev/null; then
    echo "FAIL $svc: $(systemctl is-active "$svc" 2>/dev/null || echo inactive) ($(systemctl show -p SubState --value "$svc" 2>/dev/null))"
  else
    echo "WARN $svc: not enabled"
  fi
done

section "Recent ndp logs (last 25 lines)"
journalctl -u ndp -n 25 --no-pager 2>/dev/null || echo "journalctl unavailable"

section "Recent ndp-hotspot logs"
journalctl -u ndp-hotspot -n 15 --no-pager 2>/dev/null || true

section "NDP binary / version"
if [[ -x "${NDP_ROOT}/venv/bin/ndp" ]]; then
  "${NDP_ROOT}/venv/bin/ndp" --version
else
  echo "MISSING ${NDP_ROOT}/venv/bin/ndp — run: sudo ./scripts/install.sh"
fi

section "Config file"
if [[ -f "$CONFIG" ]]; then
  echo "OK  $CONFIG exists"
  grep -E '^(ui:|  enabled:|  framebuffer:|wifi_hotspot:|  enabled:)' "$CONFIG" 2>/dev/null | head -20 || true
else
  echo "MISSING $CONFIG"
fi

section "Custom themes.json"
THEMES="${LOCALE_DIR}/themes.json"
if [[ -f "$THEMES" ]]; then
  if python3 -m json.tool "$THEMES" >/dev/null 2>&1; then
    echo "OK  JSON valid: $THEMES"
  else
    echo "FAIL invalid JSON in $THEMES — NDP may crash on startup"
    echo "     Fix: sudo mv $THEMES ${THEMES}.bad && sudo systemctl restart ndp"
  fi
else
  echo "INFO no custom themes (bundled only)"
fi

section "Display framebuffer"
for fb in /dev/fb0 /dev/fb1; do
  if [[ -e "$fb" ]]; then
    echo "OK  $fb present"
  else
    echo "---- $fb missing"
  fi
done

section "Boot target (Desktop vs Lite)"
TARGET="$(systemctl get-default 2>/dev/null || echo unknown)"
echo "default target: $TARGET"
if [[ "$TARGET" == "graphical.target" ]]; then
  echo "NOTE: Raspberry Pi Desktop is active. TFT may show the desktop instead of NDP"
  echo "      if ndp.service is not running. Prefer Pi OS Lite or: sudo systemctl set-default multi-user.target"
fi

section "Wi-Fi interface"
if command -v iw >/dev/null 2>&1; then
  IW_OUT="$(iw dev wlan0 info 2>/dev/null || true)"
  if [[ -n "$IW_OUT" ]]; then
    echo "$IW_OUT"
    if echo "$IW_OUT" | grep -q 'type AP'; then
      echo "OK  wlan0 in AP mode (hotspot)"
    elif echo "$IW_OUT" | grep -q 'type managed'; then
      echo "FAIL wlan0 in client (managed) mode — NetworkManager/wpa_supplicant took the interface"
      echo "     Fix: sudo ndp-hotspot-prestart && sudo ndp hotspot restart && iw dev wlan0 info"
    fi
  else
    echo "wlan0 not available or no driver"
  fi
else
  echo "iw not installed"
fi
OPER="$(cat /sys/class/net/wlan0/operstate 2>/dev/null || echo unknown)"
echo "operstate: $OPER"

section "Manual probe (once)"
if [[ -x "${NDP_ROOT}/venv/bin/ndp" ]]; then
  "${NDP_ROOT}/venv/bin/ndp" --config "$CONFIG" --once 2>&1 | head -15 || echo "ndp --once failed"
fi

section "Hotspot status"
if [[ -x "${NDP_ROOT}/venv/bin/ndp" ]]; then
  "${NDP_ROOT}/venv/bin/ndp" hotspot status --config "$CONFIG" 2>&1 || true
fi

echo
echo "Recovery (typical):"
echo "  sudo ndp-hotspot-prestart"
echo "  sudo ndp hotspot restart"
echo "  sudo systemctl restart ndp"
echo "  iw dev wlan0 info    # expect: type AP"
echo "  cd /opt/ndp && sudo git pull && sudo ./scripts/install.sh"
echo "  sudo journalctl -u ndp-hotspot -u ndp -n 30 --no-pager"
