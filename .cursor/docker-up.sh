#!/usr/bin/env bash
# Shared helper: make sure a Docker daemon is running in this nested VM and that
# container-to-container traffic works. Sourced by install.sh and start.sh.
#
# Two nested-container quirks are handled here:
#   1. There is no init system, so dockerd is launched by hand.
#   2. Bridged frames are pushed through nftables and dropped in this netns, so
#      same-bridge container traffic (worker <-> redpanda <-> postgres) times out
#      until we tell the kernel to stop sending bridged frames to nftables.

docker_up() {
  echo '{ "storage-driver": "fuse-overlayfs" }' | sudo tee /etc/docker/daemon.json >/dev/null

  if ! sudo docker info >/dev/null 2>&1; then
    echo "[docker-up] starting dockerd"
    sudo bash -c 'nohup dockerd >/tmp/dockerd.log 2>&1 &'
    for _ in $(seq 1 60); do
      sudo docker info >/dev/null 2>&1 && break
      sleep 1
    done
    sudo docker info >/dev/null 2>&1 || { echo "[docker-up] dockerd failed to start"; sudo tail -n 40 /tmp/dockerd.log; return 1; }
  fi

  # Let the unprivileged user reach the socket for this boot without re-login.
  sudo chmod 666 /var/run/docker.sock 2>/dev/null || true

  # Same-bridge (L2) traffic must bypass nftables, or intra-stack TCP times out.
  sudo modprobe br_netfilter 2>/dev/null || true
  sudo sysctl -w \
    net.bridge.bridge-nf-call-iptables=0 \
    net.bridge.bridge-nf-call-ip6tables=0 \
    net.bridge.bridge-nf-call-arptables=0 >/dev/null 2>&1 || true

  echo "[docker-up] docker ready: $(docker --version)"
}
