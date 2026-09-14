#!/usr/bin/env bash
# One-time repository bootstrap for the PR Triage stack.
#
# The whole product is a `docker compose` stack (broker, pipeline, model, worker,
# web). This script makes the VM able to run that stack and pre-caches everything
# slow: the container images and the ~2GB local model. It is idempotent, so it is
# safe to run again, and when environment builds are enabled it runs once and the
# result (installed Docker, built images, pulled model) is captured in the snapshot.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

log() { echo "[install] $*"; }

# ── 1. Docker + Task (stable system tooling) ────────────────────────────────
if ! command -v docker >/dev/null 2>&1; then
  log "installing Docker CE"
  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  sudo chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    -o Dpkg::Options::=--force-confold \
    docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin fuse-overlayfs
else
  log "Docker already present: $(docker --version)"
fi

if ! command -v task >/dev/null 2>&1; then
  log "installing Task (go-task)"
  sudo sh -c 'curl -fsSL https://taskfile.dev/install.sh | sh -s -- -d -b /usr/local/bin'
else
  log "Task already present: $(task --version)"
fi

# Let the unprivileged user drive Docker without sudo (group applies on next login;
# start.sh also relaxes the socket for the current boot).
sudo usermod -aG docker "$(id -un)" || true

# ── 2. Docker daemon config + a daemon to talk to during install ────────────
# The host filesystem is already an overlay, so the default overlay2 driver cannot
# stack on it inside this nested container; fuse-overlayfs can.
echo '{ "storage-driver": "fuse-overlayfs" }' | sudo tee /etc/docker/daemon.json >/dev/null

# shellcheck source=.cursor/docker-up.sh
source "$REPO_ROOT/.cursor/docker-up.sh"
docker_up   # starts dockerd if needed, applies the nested-container network fix

# ── 3. .env (Task's `setup` target does the same; keep an existing one) ──────
[ -f .env ] || { cp .env.example .env; log "created .env from .env.example"; }

# ── 4. Pre-cache images and the app build so boots are fast ─────────────────
log "building app image and pulling service images"
docker compose build
docker compose pull --ignore-pull-failures 2>/dev/null || true

# ── 5. Pre-pull the local model into the compose volume ─────────────────────
# The worker needs a model to classify live. Downloading ~2GB on every boot is
# wasteful, so pull it once here into the named volume the compose `ollama`
# service mounts, and let the snapshot carry it.
#
# It is pulled through the *default* bridge on purpose: in this nested VM only the
# default docker0 network can reach the internet, so a throwaway puller on that
# network writes the model into the shared volume that the real service reuses.
PROJECT="$(basename "$REPO_ROOT" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9')"
MODEL="$(grep -E '^OLLAMA_MODEL=' .env | cut -d= -f2)"
MODEL="${MODEL:-qwen2.5:3b}"
VOL="${PROJECT}_ollama-models"

MODEL_MANIFEST="/root/.ollama/models/manifests/registry.ollama.ai/library/${MODEL%%:*}/${MODEL##*:}"

docker volume create "$VOL" >/dev/null
if docker run --rm -v "$VOL:/root/.ollama" --entrypoint sh ollama/ollama:latest -c "test -f '$MODEL_MANIFEST'" 2>/dev/null; then
  log "model $MODEL already in $VOL"
else
  log "pulling model $MODEL into $VOL (via default bridge; ~2GB, first time only)"
  docker rm -f mpull >/dev/null 2>&1 || true
  docker run -d --name mpull --network bridge -v "$VOL:/root/.ollama" ollama/ollama:latest >/dev/null
  # Give the embedded server a moment to accept API calls.
  for _ in $(seq 1 15); do docker exec mpull ollama list >/dev/null 2>&1 && break; sleep 1; done
  # Best effort: if the model CDN is unreachable, the stack still runs from the
  # recorded fixtures and the worker waits for a model, exactly as documented.
  docker exec mpull ollama pull "$MODEL" || log "WARNING: model pull failed; UI still works from recorded fixtures (see README)"
  docker rm -f mpull >/dev/null 2>&1 || true
fi

log "done"
