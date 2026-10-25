#!/usr/bin/env python3
"""Installed on the server; updates images only, never Compose or the host."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.request

ROOT = Path('/app/fintech')
KEYS = {'backend': 'BACKEND_IMAGE', 'frontend': 'WEB_IMAGE'}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def validate(component, image, revision, sequence):
    require(component in KEYS, 'Unknown component')
    require(re.fullmatch(r'ghcr.io/ub-es-f4-2026/' + component + r'@sha256:[a-f0-9]{64}', image), 'Invalid image digest')
    require(re.fullmatch(r'[a-f0-9]{40}', revision), 'Invalid commit')
    require(sequence > 0, 'Invalid workflow sequence')


def images(text):
    result = {}
    for key in KEYS.values():
        matches = re.findall(r'^' + key + r'=(.+)$', text, re.M)
        require(len(matches) == 1, 'Expected exactly one ' + key)
        result[key] = matches[0]
    return result


def replace_image(text, component, image):
    images(text)
    return re.sub(r'^' + KEYS[component] + r'=.+$', KEYS[component] + '=' + image, text, flags=re.M)


def run(args, *, output=None, timeout=300):
    # Never echo subprocess output: configuration, migrations and DB tools may
    # include credentials or row contents in errors. Diagnose privately on host.
    result = subprocess.run(args, stdin=subprocess.DEVNULL,
                            stdout=output or subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=timeout, check=False)
    require(result.returncode == 0, 'Command failed: ' + args[0] + ' (output withheld)')
    return result.stdout.decode() if output is None else ''


def write_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def http_checks(port):
    for route in ('/', '/api/health', '/api/opportunities'):
        with urllib.request.urlopen('http://127.0.0.1:' + port + route, timeout=10) as response:
            require(response.status == 200, 'HTTP check failed')
            if route == '/api/health':
                data = json.load(response)
                require(data.get('database') == 'ok' and data.get('status') == 'ok', 'Database health failed')


def deploy(root, component, image, revision, sequence):
    validate(component, image, revision, sequence)
    marker = root / 'DEPLOYMENT_BLOCKED.json'
    require(not marker.exists(), 'Previous deployment interrupted/failed; inspect DEPLOYMENT_BLOCKED.json before continuing')
    env = root / '.env.production'
    text = env.read_text()
    previous = images(text)
    manifest = root / 'release-current.json'
    state = json.loads(manifest.read_text()) if manifest.exists() else {'sequences': {}}
    if sequence <= state['sequences'].get(component, 0):
        print('Skipped: this workflow is already deployed or older than the deployed release')
        return
    port = re.findall(r'^WEB_PORT=(\d+)$', text, re.M)
    require(len(port) == 1 and 1 <= int(port[0]) <= 65535, 'Invalid WEB_PORT')
    dc_base = ['docker', 'compose', '-p', 'fintech-prod', '--env-file', str(env), '-f', str(root / 'compose.production.yaml')]
    run(dc_base + ['config', '--quiet'])
    for service in ('db', 'backend', 'caddy'):
        ids = run(dc_base + ['ps', '-q', service]).split()
        require(len(ids) == 1, 'Expected running project service: ' + service)
        info = json.loads(run(['docker', 'inspect', '--format', '{{json .Config.Labels}}', ids[0]]))
        require(info.get('com.docker.compose.project') == 'fintech-prod' and info.get('com.docker.compose.service') == service, 'Wrong project/service')
        health = run(['docker', 'inspect', '--format', '{{.State.OOMKilled}} {{.State.Health.Status}}', ids[0]]).strip()
        require(health == 'false healthy', 'Unhealthy/OOM service; diagnose before deploying: ' + service)
    require(shutil.disk_usage(root).free > 1024**3, 'Less than 1 GiB free disk space')
    run(['docker', 'pull', image], timeout=600)
    label = run(['docker', 'image', 'inspect', '--format', '{{index .Config.Labels "org.opencontainers.image.revision"}}', image]).strip()
    require(label == revision, 'Image revision does not match tested commit')
    candidate = root / '.env.candidate'
    candidate.write_text(replace_image(text, component, image))
    candidate.chmod(0o600)
    dc = dc_base.copy()
    dc[dc.index(str(env))] = str(candidate)
    run(dc + ['config', '--quiet'])
    release_id = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '-' + component + '-' + str(sequence)
    archive = root / 'releases' / release_id
    archive.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(env, archive / 'previous.env')
    record = {'release': release_id, 'component': component, 'commit': revision,
              'previous': previous, 'images': images(candidate.read_text()),
              'compose_sha256': hashlib.sha256((root / 'compose.production.yaml').read_bytes()).hexdigest(),
              'sequences': {**state['sequences'], component: sequence}, 'status': 'in_progress'}
    write_json(archive / 'release.json', record)
    # Persist before any service mutation. A killed runner cannot silently unlock
    # an incomplete release for the next deployment.
    write_json(marker, record)
    try:
        if component == 'backend':
            print('Stopping backend; taking a private database backup', flush=True)
            run(dc_base + ['stop', 'backend'])
            with (archive / 'database.dump').open('xb') as backup:
                run(dc_base + ['exec', '-T', 'db', 'sh', '-c',
                               'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc'], output=backup)
            require((archive / 'database.dump').stat().st_size > 0, 'Empty database backup')
            # Check the archive structure, not a substitute for a restore drill.
            with (archive / 'database.dump').open('rb') as backup:
                result = subprocess.run(dc_base + ['exec', '-T', 'db', 'pg_restore', '--list'],
                                        stdin=backup, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=60)
                require(result.returncode == 0, 'Backup archive validation failed')
            print('Applying migrations', flush=True)
            run(dc + ['run', '--rm', '-T', '--interactive=false', '--no-deps', 'migrate'])
        service = 'backend' if component == 'backend' else 'caddy'
        print('Starting ' + service, flush=True)
        run(dc + ['up', '-d', '--no-deps', '--wait', '--wait-timeout', '180', service])
        # Retry briefly while the proxy reconnects to a replaced backend.
        for attempt in range(12):
            try:
                http_checks(port[0])
                break
            except Exception:
                if attempt == 11:
                    raise
                time.sleep(2)
        candidate.replace(env)
        record['status'] = 'success'
        write_json(archive / 'release.json', record)
        write_json(manifest, record)
        marker.unlink()
        print('Deployment healthy: ' + release_id)
    except BaseException:
        record['status'] = 'failed_or_interrupted'
        write_json(marker, record)
        write_json(archive / 'release.json', record)
        raise


def main():
    import fcntl  # Linux server; helpers remain testable on Windows.
    parser = argparse.ArgumentParser()
    parser.add_argument('component', choices=KEYS)
    parser.add_argument('image')
    parser.add_argument('revision')
    parser.add_argument('sequence', type=int)
    args = parser.parse_args()
    os.umask(0o077)
    # Compose must not receive stale image overrides from the caller's shell.
    for key in ('BACKEND_IMAGE', 'WEB_IMAGE', 'POSTGRES_DB', 'POSTGRES_USER', 'POSTGRES_PASSWORD', 'WEB_PORT'):
        os.environ.pop(key, None)
    with (ROOT / '.deploy.lock').open('a') as lock:
        deadline = time.monotonic() + 900
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                require(time.monotonic() < deadline, 'Timed out waiting for another deployment')
                time.sleep(2)
        deploy(ROOT, args.component, args.image, args.revision, args.sequence)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('Deployment stopped. Inspect project state and release records on server; no automatic rollback.', file=sys.stderr)
        sys.exit(1)
