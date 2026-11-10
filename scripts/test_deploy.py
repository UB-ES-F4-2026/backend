"""Offline deployment tests. No Docker, SSH or production data is used."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('deploy', Path(__file__).with_name('deploy.py'))
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)
SHA = 'a' * 40


def image(component, char='b'):
    return 'ghcr.io/ub-es-f4-2026/' + component + '@sha256:' + char * 64


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.original = ('BACKEND_IMAGE=' + image('backend', 'a') + '\nWEB_IMAGE=' + image('frontend', 'a')
                         + '\nPOSTGRES_PASSWORD=test-only-secret\nWEB_PORT=8080\n')
        (self.root / '.env.production').write_text(self.original)
        (self.root / 'compose.production.yaml').write_text('name: fintech-prod\n')
        self.calls = []
        self.failure = None
        self.project = 'fintech-prod'
        self.addCleanup(patch.stopall)
        patch.object(deploy, 'run', side_effect=self.run_command).start()
        patch.object(deploy, 'http_checks').start()
        patch.object(deploy.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)).start()
        patch.object(deploy.shutil, 'disk_usage', return_value=type('Disk', (), {'free': 10 * 1024**3})()).start()

    def run_command(self, args, **kwargs):
        self.calls.append(args)
        if self.failure and self.failure in args:
            raise RuntimeError('Simulated failure')
        if 'ps' in args:
            return args[-1] + '\n'
        if 'inspect' in args and '{{json .Config.Labels}}' in args:
            return json.dumps({'com.docker.compose.project': self.project, 'com.docker.compose.service': args[-1]})
        if '{{.State.OOMKilled}} {{.State.Health.Status}}' in args:
            return 'false healthy\n'
        if 'image' in args and 'inspect' in args:
            return SHA
        if kwargs.get('output'):
            kwargs['output'].write(b'PGDMP-test-archive')
        return ''

    def execute(self, component='backend', sequence=10):
        deploy.deploy(self.root, component, image(component), SHA, sequence)

    def test_rejects_untrusted_arguments(self):
        for bad in ['latest', image('frontend'), image('backend') + '; echo bad']:
            with self.assertRaises(RuntimeError):
                deploy.validate('backend', bad, SHA, 10)
        with self.assertRaises(RuntimeError):
            deploy.validate('backend', image('backend'), 'bad', 10)

    def test_backend_backup_migration_and_preserves_frontend_and_secrets(self):
        self.execute()
        text = (self.root / '.env.production').read_text()
        self.assertIn('WEB_IMAGE=' + image('frontend', 'a'), text)
        self.assertIn('POSTGRES_PASSWORD=test-only-secret', text)
        self.assertFalse((self.root / 'DEPLOYMENT_BLOCKED.json').exists())
        record = json.loads((self.root / 'release-current.json').read_text())
        self.assertEqual(record['images']['BACKEND_IMAGE'], image('backend'))
        self.assertNotIn('test-only-secret', json.dumps(record))
        self.assertEqual(len(list((self.root / 'releases').glob('*/database.dump'))), 1)
        stop = next(i for i, c in enumerate(self.calls) if 'stop' in c)
        backup = next(i for i, c in enumerate(self.calls) if any('pg_dump' in a for a in c))
        migration = next(i for i, c in enumerate(self.calls) if 'migrate' in c)
        start = next(i for i, c in enumerate(self.calls) if 'up' in c)
        self.assertLess(stop, backup)
        self.assertLess(backup, migration)
        self.assertLess(migration, start)
        self.assertIn('--no-deps', self.calls[start])

    def test_frontend_does_not_stop_or_migrate_backend(self):
        self.execute('frontend')
        self.assertFalse(any('stop' in c or 'migrate' in c for c in self.calls))
        self.assertIn('BACKEND_IMAGE=' + image('backend', 'a'), (self.root / '.env.production').read_text())
        self.assertEqual(next(c for c in self.calls if 'up' in c)[-1], 'caddy')

    def test_old_run_cannot_roll_back_new_release(self):
        self.execute()
        self.calls.clear()
        self.execute(sequence=9)
        self.assertEqual(self.calls, [])

    def test_front_and_back_preserve_each_others_sequence(self):
        self.execute()
        self.execute('frontend', 2)
        record = json.loads((self.root / 'release-current.json').read_text())
        self.assertEqual(record['sequences'], {'backend': 10, 'frontend': 2})
        self.assertEqual(record['images']['BACKEND_IMAGE'], image('backend'))

    def test_failed_migration_blocks_following_deployments(self):
        self.failure = 'migrate'
        with self.assertRaises(RuntimeError):
            self.execute()
        self.assertEqual((self.root / '.env.production').read_text(), self.original)
        self.assertTrue((self.root / 'DEPLOYMENT_BLOCKED.json').exists())
        self.assertFalse(any('up' in c for c in self.calls))
        self.calls.clear()
        with self.assertRaises(RuntimeError):
            self.execute('frontend')
        self.assertEqual(self.calls, [])

    def test_failed_pull_does_not_stop_service(self):
        self.failure = 'pull'
        with self.assertRaises(RuntimeError):
            self.execute()
        self.assertFalse(any('stop' in c for c in self.calls))
        self.assertFalse((self.root / 'DEPLOYMENT_BLOCKED.json').exists())

    def test_wrong_project_refused(self):
        self.project = 'another-project'
        with self.assertRaises(RuntimeError):
            self.execute()
        self.assertFalse(any('stop' in c for c in self.calls))

    def test_duplicate_env_key_refused(self):
        with self.assertRaises(RuntimeError):
            deploy.replace_image(self.original + 'BACKEND_IMAGE=bad\n', 'backend', image('backend'))

    def test_backup_failure_never_runs_migrations(self):
        self.failure = 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc'
        with self.assertRaises(RuntimeError):
            self.execute()
        self.assertFalse(any('migrate' in c for c in self.calls))
        self.assertTrue((self.root / 'DEPLOYMENT_BLOCKED.json').exists())

    def test_http_failure_does_not_commit_release(self):
        with patch.object(deploy, 'http_checks', side_effect=RuntimeError('HTTP failure')), patch.object(deploy.time, 'sleep'):
            with self.assertRaises(RuntimeError):
                self.execute('frontend')
        self.assertFalse((self.root / 'release-current.json').exists())
        self.assertEqual((self.root / '.env.production').read_text(), self.original)
        self.assertTrue((self.root / 'DEPLOYMENT_BLOCKED.json').exists())

    def test_wrong_image_revision_refused_before_mutation(self):
        with self.assertRaises(RuntimeError):
            deploy.deploy(self.root, 'backend', image('backend'), 'c' * 40, 10)
        self.assertFalse(any('stop' in c for c in self.calls))


if __name__ == '__main__':
    unittest.main()
