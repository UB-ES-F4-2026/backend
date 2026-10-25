#!/usr/bin/env bash
set -euo pipefail
for name in DEPLOY_HOST DEPLOY_USER DEPLOY_PORT DEPLOY_KNOWN_HOSTS DEPLOY_SSH_KEY IMAGE COMPONENT GITHUB_SHA GITHUB_RUN_NUMBER; do
  [[ -n "${!name:-}" ]] || { echo "::error::Missing $name"; exit 1; }
done
[[ "$DEPLOY_HOST" =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]*$ ]]
[[ "$DEPLOY_USER" =~ ^[a-z_][a-z0-9_-]*$ ]]
[[ "$DEPLOY_PORT" =~ ^[0-9]{1,5}$ ]]
(( 10#$DEPLOY_PORT >= 1 && 10#$DEPLOY_PORT <= 65535 ))
[[ "$COMPONENT" == backend || "$COMPONENT" == frontend ]]
[[ "$IMAGE" =~ ^ghcr.io/ub-es-f4-2026/$COMPONENT@sha256:[a-f0-9]{64}$ ]]
[[ "$GITHUB_SHA" =~ ^[a-f0-9]{40}$ ]]
[[ "$GITHUB_RUN_NUMBER" =~ ^[0-9]+$ ]]
umask 077
ssh_dir=$(mktemp -d "$RUNNER_TEMP/fintech-ssh.XXXXXX")
trap 'rm -f -- "$ssh_dir/key" "$ssh_dir/known_hosts"; rmdir -- "$ssh_dir"' EXIT
printf '%s\n' "$DEPLOY_SSH_KEY" | tr -d '\r' > "$ssh_dir/key"
printf '%s\n' "$DEPLOY_KNOWN_HOSTS" | tr -d '\r' > "$ssh_dir/known_hosts"
unset DEPLOY_SSH_KEY
ssh-keygen -y -P '' -f "$ssh_dir/key" > /dev/null
ssh -F /dev/null -T -p "$DEPLOY_PORT" -i "$ssh_dir/key" \
  -o BatchMode=yes -o IdentitiesOnly=yes -o IdentityAgent=none \
  -o StrictHostKeyChecking=yes -o UpdateHostKeys=no \
  -o "UserKnownHostsFile=$ssh_dir/known_hosts" -o GlobalKnownHostsFile=/dev/null \
  -o ConnectTimeout=15 -o ServerAliveInterval=15 -o ServerAliveCountMax=3 \
  "$DEPLOY_USER@$DEPLOY_HOST" \
  "python3 /app/fintech/deploy.py '$COMPONENT' '$IMAGE' '$GITHUB_SHA' '$GITHUB_RUN_NUMBER'" < /dev/null
printf '### Deployment verified\nComponent: %s\nCommit: %s\nImage: %s\n' "$COMPONENT" "$GITHUB_SHA" "$IMAGE" >> "$GITHUB_STEP_SUMMARY"
