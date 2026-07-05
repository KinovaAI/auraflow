#!/usr/bin/env bash
# Convenience wrapper around docker compose for AuraFlow.
# Equivalent to plain `docker compose ...` — the repo only has one compose
# file (docker-compose.yml) and it loads .env.prod for every service.
#
# Usage:
#   ./deploy.sh build api
#   ./deploy.sh up api
#   ./deploy.sh recreate api
#   ./deploy.sh logs api
#   ./deploy.sh ps

set -euo pipefail

cd "$(dirname "$0")"

cmd="${1:-}"
shift || true

case "$cmd" in
  build)     sudo docker compose build "$@" ;;
  up)        sudo docker compose up -d "$@" ;;
  up-all)    sudo docker compose up -d ;;
  recreate)  sudo docker compose up -d --force-recreate "$@" ;;
  restart)   sudo docker compose restart "$@" ;;
  down)      sudo docker compose down ;;
  logs)      sudo docker compose logs -f "$@" ;;
  ps|status) sudo docker compose ps ;;
  *)
    echo "Usage: $0 {build|up|up-all|recreate|restart|down|logs|ps} [services...]" >&2
    exit 2
    ;;
esac
