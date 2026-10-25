#!/usr/bin/env bash
# First installation only. Execute on the server as alex, after uploading Compose.
set -euo pipefail
umask 077
cd /app/fintech
exec 9>.deploy.lock
flock -n 9 || { echo 'Another deployment is running'; exit 1; }
test ! -e .env.production || { echo 'Existing installation: use the update procedure'; exit 1; }
test -z "$(docker ps -aq --filter label=com.docker.compose.project=fintech-prod)"
test -z "$(docker volume ls -q --filter name=fintech-prod_postgres_data)"
test -z "$(ss -H -ltn 'sport = :8080')"
test -f compose.production.yaml.upload
mv -n compose.production.yaml.upload compose.production.yaml
test ! -e compose.production.yaml.upload

backend='ghcr.io/ub-es-f4-2026/backend@sha256:3a5f145a66ddba75993c3d198aa082a14acadc4a90aee5c16d3881be97948dc0'
web='ghcr.io/ub-es-f4-2026/frontend@sha256:6bec5b608f9324807c152beb783f3b8995dbe7f002fa03766a6e9b641ea732a0'
password=$(openssl rand -hex 32)
(set -o noclobber; printf 'BACKEND_IMAGE=%s\nWEB_IMAGE=%s\nPOSTGRES_DB=fintech\nPOSTGRES_USER=fintech\nPOSTGRES_PASSWORD=%s\nWEB_PORT=8080\n' "$backend" "$web" "$password" > .env.production)
unset password
chmod 600 .env.production
dc() { docker compose -p fintech-prod --env-file .env.production -f compose.production.yaml "$@"; }
dc config --quiet
dc --profile tools pull
dc up -d --wait --wait-timeout 120 db
dc run --rm -T --interactive=false migrate
dc up -d --wait --wait-timeout 180 backend caddy
curl --fail --silent --show-error http://127.0.0.1:8080/api/health
printf '\n'
curl --fail --silent --show-error http://127.0.0.1:8080/ -o /dev/null
{
  date -u '+DEPLOYED_AT=%Y-%m-%dT%H:%M:%SZ'
  printf 'BACKEND_IMAGE=%s\nWEB_IMAGE=%s\n' "$backend" "$web"
  sha256sum compose.production.yaml
  dc exec -T backend python -m alembic current < /dev/null
} > release-first.txt
dc ps
