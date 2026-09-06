#!/usr/bin/env bash
# Per-boot startup for the PR Triage stack.
#
# Starts the Docker daemon, re-applies the nested-container network fix, and brings
# the compose stack up. Images and the model are already cached by install.sh (and
# by the snapshot when builds are enabled), so this is fast and just reconciles
# running containers. Safe to run repeatedly.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# shellcheck source=.cursor/docker-up.sh
source "$REPO_ROOT/.cursor/docker-up.sh"
docker_up

[ -f .env ] || cp .env.example .env

echo "[start] bringing up the stack"
# Not --wait: the model download one-shot and the GitHub poller degrade gracefully
# in this network (documented in the README), so waiting on every service to be
# healthy would be wrong. Postgres + web + the broker come up regardless.
docker compose up -d

echo "[start] stack is up. Web UI on :8000, Redpanda console on :8080."
echo "[start] recorded rows load automatically; run 'task seed' for a live model pass."
