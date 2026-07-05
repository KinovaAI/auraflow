#!/usr/bin/env bash
set -euo pipefail

# ================================================
# AuraFlow Production Deployment Script
# ================================================
# Usage:
#   ./infra/scripts/deploy.sh          — Full deploy (build + restart + nginx)
#   ./infra/scripts/deploy.sh build    — Build images only
#   ./infra/scripts/deploy.sh restart  — Restart services only
#   ./infra/scripts/deploy.sh nginx    — Deploy nginx config only
#   ./infra/scripts/deploy.sh status   — Check service health

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.prod.yml"
ENV_FILE="$PROJECT_DIR/.env.prod"
NGINX_CONF="$PROJECT_DIR/infra/nginx/nginx.prod.conf"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()   { echo -e "${GREEN}[DEPLOY]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

check_prereqs() {
    if [[ ! -f "$ENV_FILE" ]]; then
        error ".env.prod not found. Copy .env.prod.example and fill in values."
        exit 1
    fi

    if ! command -v docker &>/dev/null; then
        error "Docker not found"
        exit 1
    fi

    if ! docker compose version &>/dev/null; then
        error "Docker Compose V2 not found"
        exit 1
    fi
}

build_images() {
    log "Building production images..."
    cd "$PROJECT_DIR"
    docker compose -f "$COMPOSE_FILE" build --parallel
    log "Build complete"
}

restart_services() {
    log "Stopping existing services..."
    cd "$PROJECT_DIR"
    docker compose -f "$COMPOSE_FILE" down --remove-orphans 2>/dev/null || true

    log "Starting production services..."
    docker compose -f "$COMPOSE_FILE" up -d

    log "Waiting for health checks..."
    local retries=30
    local count=0
    while [[ $count -lt $retries ]]; do
        if docker compose -f "$COMPOSE_FILE" ps --format json 2>/dev/null | grep -q '"unhealthy"'; then
            sleep 2
            count=$((count + 1))
        else
            break
        fi
    done

    log "Services started"
    docker compose -f "$COMPOSE_FILE" ps
}

deploy_nginx() {
    log "Deploying nginx configuration..."

    if [[ ! -f "$NGINX_CONF" ]]; then
        error "Nginx config not found: $NGINX_CONF"
        exit 1
    fi

    # Test config syntax
    sudo cp "$NGINX_CONF" /etc/nginx/nginx.conf
    if sudo nginx -t 2>&1; then
        sudo systemctl reload nginx
        log "Nginx reloaded successfully"
    else
        error "Nginx config test failed — rolling back"
        sudo systemctl reload nginx 2>/dev/null || true
        exit 1
    fi
}

check_status() {
    log "Service status:"
    cd "$PROJECT_DIR"
    docker compose -f "$COMPOSE_FILE" ps

    echo ""
    log "Health checks:"

    # API
    if curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1; then
        echo -e "  API:    ${GREEN}healthy${NC}"
    else
        echo -e "  API:    ${RED}down${NC}"
    fi

    # Web
    if curl -sf http://127.0.0.1:3000/ >/dev/null 2>&1; then
        echo -e "  Web:    ${GREEN}healthy${NC}"
    else
        echo -e "  Web:    ${RED}down${NC}"
    fi

    # PostgreSQL
    if docker exec auraflow_postgres pg_isready -U auraflow -d auraflow >/dev/null 2>&1; then
        echo -e "  DB:     ${GREEN}healthy${NC}"
    else
        echo -e "  DB:     ${RED}down${NC}"
    fi

    # Redis
    if docker inspect --format='{{.State.Health.Status}}' auraflow_redis 2>/dev/null | grep -q healthy; then
        echo -e "  Redis:  ${GREEN}healthy${NC}"
    else
        echo -e "  Redis:  ${RED}down${NC}"
    fi

    # Nginx
    if systemctl is-active --quiet nginx 2>/dev/null; then
        echo -e "  Nginx:  ${GREEN}running${NC}"
    else
        echo -e "  Nginx:  ${RED}stopped${NC}"
    fi

    # SSL
    echo ""
    log "SSL certificate:"
    if [[ -f /etc/letsencrypt/live/auraflow.fit/fullchain.pem ]]; then
        local expiry
        expiry=$(openssl x509 -enddate -noout -in /etc/letsencrypt/live/auraflow.fit/fullchain.pem 2>/dev/null | cut -d= -f2)
        echo -e "  Expires: ${GREEN}$expiry${NC}"
    else
        echo -e "  ${YELLOW}No SSL cert found${NC}"
    fi
}

run_migrations() {
    log "Running database migrations..."
    cd "$PROJECT_DIR"
    docker compose -f "$COMPOSE_FILE" exec api alembic upgrade head
    log "Migrations complete"
}

# ── Main ─────────────────────────────────────────
check_prereqs

case "${1:-full}" in
    build)
        build_images
        ;;
    restart)
        restart_services
        ;;
    nginx)
        deploy_nginx
        ;;
    status)
        check_status
        ;;
    migrate)
        run_migrations
        ;;
    full)
        build_images
        restart_services
        deploy_nginx
        run_migrations
        echo ""
        check_status
        echo ""
        log "Deployment complete!"
        ;;
    *)
        echo "Usage: $0 {build|restart|nginx|status|migrate|full}"
        exit 1
        ;;
esac
