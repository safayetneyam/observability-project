#!/usr/bin/env bash
# One-time host preparation for a fresh Ubuntu 24.04/26.04 machine (laptop or EC2).
# Installs Docker Engine + Compose plugin (official Docker apt repo) and MicroK8s (snap),
# enables the add-ons this project needs, and adds the current user to the right groups.
#   sudo ./scripts/setup-ubuntu.sh   then log out and back in (or run: newgrp docker)
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "run with sudo"; exit 1; }
TARGET_USER="${SUDO_USER:-ubuntu}"
MICROK8S_CHANNEL="${MICROK8S_CHANNEL:-1.31/stable}"

echo "==> Docker Engine + Compose plugin"
if ! command -v docker >/dev/null; then
  apt-get update -y
  apt-get install -y ca-certificates curl gnupg
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${UBUNTU_CODENAME:-$VERSION_CODENAME} stable" \
    >/etc/apt/sources.list.d/docker.list
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
systemctl enable --now docker
usermod -aG docker "$TARGET_USER"

echo "==> MicroK8s ($MICROK8S_CHANNEL)"
if ! command -v microk8s >/dev/null; then
  snap install microk8s --classic --channel="$MICROK8S_CHANNEL"
fi
usermod -aG microk8s "$TARGET_USER"
mkdir -p "/home/$TARGET_USER/.kube" && chown -R "$TARGET_USER" "/home/$TARGET_USER/.kube"
microk8s status --wait-ready
microk8s enable dns
microk8s enable hostpath-storage
microk8s enable helm3
snap alias microk8s.kubectl kubectl 2>/dev/null || true

echo "==> Helpful tools"
apt-get install -y jq bc curl zip

echo
docker --version
docker compose version
microk8s version
echo "Done. Log out/in so '$TARGET_USER' picks up the docker and microk8s groups."
