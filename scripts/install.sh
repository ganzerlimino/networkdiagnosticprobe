#!/usr/bin/env bash
# Install NDP on Raspberry Pi OS Lite (or Debian-based systems).
#
# Optional Joy-it RB-TFT3.2 display driver:
#   sudo ./scripts/install.sh --with-display
#   sudo NDP_INSTALL_DISPLAY=1 ./scripts/install.sh
set -euo pipefail

NDP_USER="${NDP_USER:-root}"
NDP_ROOT="${NDP_ROOT:-/opt/ndp}"
NDP_CONFIG_DIR="${NDP_CONFIG_DIR:-/etc/ndp}"
NDP_INSTALL_DISPLAY="${NDP_INSTALL_DISPLAY:-}"
NDP_LCD_SHOW_DIR="${NDP_LCD_SHOW_DIR:-/opt/lcd-show}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WITH_DISPLAY=0

usage() {
  cat <<'EOF'
Usage: sudo ./scripts/install.sh [options]

Options:
  --with-display   Install Joy-it RB-TFT3.2 driver via LCD-show (reboots the Pi)
  -h, --help       Show this help

Environment:
  NDP_INSTALL_DISPLAY=1   Same as --with-display (set 0 to skip interactive prompt)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-display)
      WITH_DISPLAY=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo $0" >&2
  exit 1
fi

install_joyit_display() {
  echo "==> [Optional] Joy-it RB-TFT3.2 display driver (LCD-show)"
  echo "    Repository: https://github.com/goodtft/LCD-show"
  echo "    WARNING: LCD32-show reboots the Raspberry Pi when it finishes."
  echo "    NDP services are already installed and will start after reboot."

  DEBIAN_FRONTEND=noninteractive apt-get install -y git

  if [[ ! -x "${NDP_LCD_SHOW_DIR}/LCD32-show" ]]; then
    rm -rf "${NDP_LCD_SHOW_DIR}"
    git clone --depth 1 https://github.com/goodtft/LCD-show.git "${NDP_LCD_SHOW_DIR}"
    chmod -R 755 "${NDP_LCD_SHOW_DIR}"
  fi

  echo "    Running LCD32-show (expect automatic reboot)..."
  (cd "${NDP_LCD_SHOW_DIR}" && ./LCD32-show)
}

maybe_install_display() {
  if [[ "${WITH_DISPLAY}" == "1" ]] || [[ "${NDP_INSTALL_DISPLAY}" == "1" ]]; then
    install_joyit_display
    return
  fi

  if [[ "${NDP_INSTALL_DISPLAY}" == "0" ]]; then
    return
  fi

  if [[ -t 0 ]]; then
    echo
    read -r -p "Install Joy-it RB-TFT3.2 display driver now? [y/N] " reply
    if [[ "${reply}" =~ ^[Yy]$ ]]; then
      install_joyit_display
    else
      echo "    Skipped display driver. You can run later:"
      echo "      sudo ./scripts/install.sh --with-display"
      echo "    Or manually: git clone https://github.com/goodtft/LCD-show.git && cd LCD-show && sudo ./LCD32-show"
    fi
  fi
}

echo "==> Installing system packages"
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  python3 \
  python3-venv \
  python3-pip \
  git \
  lldpd \
  iproute2 \
  ethtool \
  arp-scan \
  iputils-ping \
  python3-lgpio \
  python3-pygame \
  fonts-dejavu-core \
  libsdl2-2.0-0 \
  hostapd \
  dnsmasq \
  iw \
  wireless-tools \
  rfkill

echo "==> Preparing install directory at ${NDP_ROOT}"
systemctl stop ndp.service 2>/dev/null || true

install -d -m 0755 "${NDP_ROOT}"
rsync -a --delete \
  --exclude '.git' \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude 'tests' \
  "${REPO_DIR}/" "${NDP_ROOT}/"

echo "==> Creating Python virtual environment (with system GPIO/pygame packages)"
python3 -m venv --system-site-packages "${NDP_ROOT}/venv"
"${NDP_ROOT}/venv/bin/pip" install --upgrade pip
"${NDP_ROOT}/venv/bin/pip" install "${NDP_ROOT}[ui,web]"

echo "==> Verifying Python dependencies"
"${NDP_ROOT}/venv/bin/python" -c "import lgpio, pygame; print('lgpio and pygame OK')"

if [[ ! -x "${NDP_ROOT}/venv/bin/ndp" ]]; then
  echo "ERROR: ${NDP_ROOT}/venv/bin/ndp missing after install" >&2
  exit 1
fi

echo "==> Installing ndp CLI symlink"
install -d -m 0755 /usr/local/bin
ln -sf "${NDP_ROOT}/venv/bin/ndp" /usr/local/bin/ndp
install -m 0755 "${REPO_DIR}/scripts/ndp-doctor.sh" /usr/local/bin/ndp-doctor

echo "==> Installing configuration"
install -d -m 0755 "${NDP_CONFIG_DIR}"
install -m 0644 "${NDP_ROOT}/ndp/config/default.yaml" "${NDP_CONFIG_DIR}/config.yaml.example"
if [[ ! -f "${NDP_CONFIG_DIR}/config.yaml" ]]; then
  install -m 0644 "${NDP_ROOT}/ndp/config/default.yaml" "${NDP_CONFIG_DIR}/config.yaml"
else
  "${NDP_ROOT}/venv/bin/python" <<'PY'
from pathlib import Path
from ndp.core.config_merge import append_missing_config_keys

config_path = Path("/etc/ndp/config.yaml")
default_path = Path("/opt/ndp/ndp/config/default.yaml")
if append_missing_config_keys(config_path, default_path):
    print("Appended missing keys (with comments) to /etc/ndp/config.yaml")
print("Reference template with all comments: /etc/ndp/config.yaml.example")
PY
fi

echo "==> Installing locale and scenario presets"
install -d -m 0755 "${NDP_CONFIG_DIR}/locale" "${NDP_CONFIG_DIR}/scenarios"
for locale_file in "${NDP_ROOT}/ndp/locale/"*.json; do
  base="$(basename "${locale_file}")"
  if [[ "${base}" == "themes.json" ]]; then
    if [[ ! -f "${NDP_CONFIG_DIR}/locale/themes.json" ]]; then
      install -m 0644 "${locale_file}" "${NDP_CONFIG_DIR}/locale/"
    else
      echo "Keeping existing ${NDP_CONFIG_DIR}/locale/themes.json (custom themes)"
      if ! python3 -m json.tool "${NDP_CONFIG_DIR}/locale/themes.json" >/dev/null 2>&1; then
        echo "WARNING: ${NDP_CONFIG_DIR}/locale/themes.json is invalid JSON — fix or remove it" >&2
      fi
    fi
  else
    install -m 0644 "${locale_file}" "${NDP_CONFIG_DIR}/locale/"
  fi
done
install -m 0644 "${NDP_ROOT}/ndp/scenarios/profiles.yaml" "${NDP_CONFIG_DIR}/scenarios/profiles.yaml"

echo "==> Enabling lldpd"
LLDPD_DEFAULT="/etc/default/lldpd"
if [[ -f "${LLDPD_DEFAULT}" ]]; then
  if grep -q '^DAEMON_ARGS=' "${LLDPD_DEFAULT}"; then
    sed -i 's/^DAEMON_ARGS=.*/DAEMON_ARGS="-c -s"/' "${LLDPD_DEFAULT}"
  else
    echo 'DAEMON_ARGS="-c -s"' >> "${LLDPD_DEFAULT}"
  fi
else
  echo 'DAEMON_ARGS="-c -s"' > "${LLDPD_DEFAULT}"
fi
install -d -m 0755 /etc/lldpd.d
cat > /etc/lldpd.d/ndp.conf <<'EOF'
# NDP: neighbor discovery on Ethernet (skip wlan0 hotspot)
configure system interface pattern eth*
EOF
systemctl enable --now lldpd
systemctl restart lldpd

echo "==> Preparing Wi-Fi hotspot tools (hostapd + dnsmasq)"
systemctl unmask hostapd dnsmasq 2>/dev/null || true
systemctl disable --now hostapd.service dnsmasq.service 2>/dev/null || true
systemctl disable --now wpa_supplicant@wlan0.service 2>/dev/null || true
install -d -m 0755 /etc/NetworkManager/conf.d
cat > /etc/NetworkManager/conf.d/ndp-wlan0.conf <<'EOF'
# NDP owns wlan0 for phone hotspot (AP mode). Do not let NM manage this interface.
[keyfile]
unmanaged-devices=interface-name:wlan0
EOF
if [[ -f /etc/dhcpcd.conf ]] && ! grep -q '^denyinterfaces wlan0' /etc/dhcpcd.conf; then
  echo 'denyinterfaces wlan0' >> /etc/dhcpcd.conf
fi
if command -v nmcli >/dev/null 2>&1; then
  nmcli device set wlan0 managed no 2>/dev/null || true
  systemctl reload NetworkManager 2>/dev/null || true
fi
rfkill unblock all 2>/dev/null || true
rfkill unblock wifi 2>/dev/null || true
install -m 0755 "${REPO_DIR}/scripts/hotspot-prestart.sh" /usr/local/bin/ndp-hotspot-prestart

echo "==> Installing systemd units"
install -m 0644 "${NDP_ROOT}/systemd/ndp-hotspot.service" /etc/systemd/system/ndp-hotspot.service
install -m 0644 "${NDP_ROOT}/systemd/ndp.service" /etc/systemd/system/ndp.service
systemctl daemon-reload
systemctl enable ndp-hotspot.service
systemctl restart ndp-hotspot.service
systemctl enable --now ndp.service

maybe_install_display

echo
echo "NDP installed successfully."
echo "  Repo    : edit in ~/networkdiagnosticprobe, then: sudo ./scripts/install.sh"
echo "  Runtime : ${NDP_ROOT} (copia usata da systemd — non fare git pull lì)"
echo "  Service : systemctl status ndp"
echo "  Hotspot : systemctl status ndp-hotspot && ndp hotspot status"
echo "  Phone   : connect to SSID NDP-XXXX, open http://192.168.50.1:8080/"
echo "  Display : ndp test display --color cycle"
echo "  One-shot: ${NDP_ROOT}/venv/bin/ndp --once"
echo "  JSON    : ${NDP_ROOT}/venv/bin/ndp --once --json"
echo "  Up/Down : ${NDP_ROOT}/venv/bin/ndp discover updown"
