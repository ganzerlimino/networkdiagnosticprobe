#!/usr/bin/env bash
# Install NDP on Raspberry Pi OS Lite (or Debian-based systems).
set -euo pipefail

NDP_USER="${NDP_USER:-root}"
NDP_ROOT="${NDP_ROOT:-/opt/ndp}"
NDP_CONFIG_DIR="${NDP_CONFIG_DIR:-/etc/ndp}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo $0" >&2
  exit 1
fi

echo "==> Installing system packages"
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  python3 \
  python3-venv \
  python3-pip \
  lldpd \
  iproute2 \
  ethtool \
  arp-scan \
  python3-lgpio \
  python3-pygame \
  fonts-dejavu-core \
  libsdl2-2.0-0

echo "==> Preparing install directory at ${NDP_ROOT}"
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
"${NDP_ROOT}/venv/bin/pip" install "${NDP_ROOT}[ui]"

echo "==> Verifying Python dependencies"
"${NDP_ROOT}/venv/bin/python" -c "import lgpio, pygame; print('lgpio and pygame OK')"

echo "==> Installing configuration"
install -d -m 0755 "${NDP_CONFIG_DIR}"
if [[ ! -f "${NDP_CONFIG_DIR}/config.yaml" ]]; then
  install -m 0644 "${NDP_ROOT}/ndp/config/default.yaml" "${NDP_CONFIG_DIR}/config.yaml"
fi

echo "==> Enabling lldpd"
systemctl enable --now lldpd

echo "==> Installing systemd unit"
install -m 0644 "${NDP_ROOT}/systemd/ndp.service" /etc/systemd/system/ndp.service
systemctl daemon-reload
systemctl enable --now ndp.service

echo
echo "NDP installed successfully."
echo "  Service : systemctl status ndp"
echo "  One-shot: ${NDP_ROOT}/venv/bin/ndp --once"
echo "  JSON    : ${NDP_ROOT}/venv/bin/ndp --once --json"
echo "  Up/Down : ${NDP_ROOT}/venv/bin/ndp discover updown"
