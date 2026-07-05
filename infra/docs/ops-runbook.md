# AuraFlow Operations Runbook

## 1. Service Management

### Start/Stop/Restart All Services

```bash
# Start all services (build and detach)
docker compose -f docker-compose.prod.yml up -d --build

# Stop all services
docker compose -f docker-compose.prod.yml down

# Restart all services
docker compose -f docker-compose.prod.yml restart
```

### Restart Individual Service

```bash
docker compose -f docker-compose.prod.yml restart api
docker compose -f docker-compose.prod.yml restart web
docker compose -f docker-compose.prod.yml restart celery_worker
```

### View Logs

```bash
# Follow logs for a specific service (last 100 lines)
docker compose -f docker-compose.prod.yml logs -f api --tail=100

# All services
docker compose -f docker-compose.prod.yml logs -f --tail=100
```

### Check Health

```bash
curl http://localhost:8000/health
```

---

## 2. Database Operations

### Connect to Database

```bash
sudo docker exec -it auraflow_postgres psql -U auraflow -d auraflow
```

### Run Migrations

```bash
sudo docker exec auraflow_api alembic upgrade head
```

### Manual Backup

```bash
sudo docker exec auraflow_postgres pg_dump -U auraflow auraflow | gzip > backup_$(date +%Y%m%d).sql.gz
```

### Check Database Size

```sql
SELECT pg_size_pretty(pg_database_size('auraflow'));
```

### Check Active Connections

```sql
SELECT count(*) AS total_connections,
       state,
       usename
FROM pg_stat_activity
WHERE datname = 'auraflow'
GROUP BY state, usename
ORDER BY total_connections DESC;
```

---

## 3. Monitoring

| Service          | URL                                    |
|------------------|----------------------------------------|
| Celery Flower    | http://localhost:5555                   |
| API Health       | https://api.auraflow.fit/health        |
| API Readiness    | https://api.auraflow.fit/health/ready  |

### Nginx Status

```bash
sudo nginx -t && sudo systemctl status nginx
```

---

## 4. SSL Certificate Renewal

### Check Auto-Renewal

```bash
sudo certbot renew --dry-run
```

### Force Renewal

```bash
sudo certbot renew --force-renewal
```

After renewal, reload Nginx:

```bash
sudo systemctl reload nginx
```

---

## 5. Common Issues & Fixes

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| CORS errors in browser | Allowed origins misconfigured | Check `CORS_ORIGINS` in `.env.prod`, restart api |
| 502 Bad Gateway | API container is down | `docker compose -f docker-compose.prod.yml restart api` |
| Database connection errors | Postgres container unhealthy | `docker compose -f docker-compose.prod.yml restart postgres` and check logs |
| Redis connection errors | Redis container down or wrong password | Check redis container, verify `REDIS_PASSWORD` in `.env.prod` |
| Login returns 500 | Missing database columns | Run migrations: `sudo docker exec auraflow_api alembic upgrade head` |

---

## 6. Emergency Procedures

### Full Restart

```bash
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d
```

### Database Restore from Backup

```bash
# 1. Stop the API to prevent writes
docker compose -f docker-compose.prod.yml stop api celery_worker

# 2. Drop and recreate the database
sudo docker exec -it auraflow_postgres psql -U auraflow -d postgres \
  -c "DROP DATABASE auraflow;" \
  -c "CREATE DATABASE auraflow OWNER auraflow;"

# 3. Restore from backup
gunzip -c backup_YYYYMMDD.sql.gz | sudo docker exec -i auraflow_postgres psql -U auraflow -d auraflow

# 4. Restart services
docker compose -f docker-compose.prod.yml up -d
```

### Rollback Deployment

```bash
git revert HEAD
docker compose -f docker-compose.prod.yml up -d --build api web
```

---

## 7. Secrets Rotation

### APP_SECRET (JWT Signing Key)

1. Generate a new secret: `openssl rand -hex 32`
2. Update `APP_SECRET` in `.env.prod`
3. Restart the API: `docker compose -f docker-compose.prod.yml restart api`

**Note:** This invalidates all existing JWTs. All users will need to log in again.

### Database Password

1. Update password in `.env.prod` (`POSTGRES_PASSWORD`)
2. Change password in Postgres: `ALTER USER auraflow WITH PASSWORD 'new_password';`
3. Restart all services: `docker compose -f docker-compose.prod.yml down && docker compose -f docker-compose.prod.yml up -d`

### Redis Password

1. Update `REDIS_PASSWORD` in `.env.prod`
2. Update the Redis `requirepass` configuration or command in `docker-compose.prod.yml`
3. Restart all services: `docker compose -f docker-compose.prod.yml down && docker compose -f docker-compose.prod.yml up -d`
