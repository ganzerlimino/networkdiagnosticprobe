#!/usr/bin/env bash
# Helper notes/script for building a flash-ready Raspberry Pi image.
#
# Full custom images are typically produced with pi-gen. This script documents
# the post-boot steps that a pi-gen custom stage can run automatically.
set -euo pipefail

cat <<'EOF'
NDP SD image build (overview)
=============================

Goal: flash SD card -> boot Pi 3 -> NDP runs automatically.

Recommended path:
1. Use Raspberry Pi Imager with Raspberry Pi OS Lite (64-bit).
2. In Imager "OS customization", set:
   - hostname: ndp
   - enable SSH (optional, for development)
   - user/password as needed
3. First boot on hardware, then run:
     curl -fsSL https://raw.githubusercontent.com/.../main/scripts/install.sh | sudo bash
   or copy this repository to the Pi and run:
     sudo ./scripts/install.sh

For a true out-of-the-box release, automate install.sh inside a pi-gen
custom stage so the image already contains:
  - lldpd enabled
  - /opt/ndp virtualenv
  - /etc/ndp/config.yaml
  - ndp.service enabled

Next repository milestone: add a pi-gen stage under image/pi-gen/.

Quick validation on a running Pi:
  sudo systemctl status lldpd ndp
  ndp --once --json
EOF
