import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch, Mock

from update_cleanup import cleanup, validate_workspace


class CleanupSafetyTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.target = self.root/'installed'
        self.target.mkdir()
        (self.target/'settings.json').write_text('keep')
        self.work = self.root/'.e7-update-test'
        self.work.mkdir()
        (self.work/'result.json').write_text(json.dumps({'ok': True}))
        (self.work/'plan.json').write_text(json.dumps({'target': str(self.target)}))

    def test_unrelated_workspace_and_mismatched_plan_are_rejected(self):
        for work in (self.target, self.root, self.root/'other'):
            with self.subTest(path=work), self.assertRaises(ValueError):
                validate_workspace(work, self.target)
        (self.work/'plan.json').write_text(json.dumps({'target': str(self.root/'other')}))
        with self.assertRaises(ValueError):
            validate_workspace(self.work, self.target)

    def test_worker_timeout_does_not_delete_staging_or_installation(self):
        with patch('update_cleanup.wait_worker', side_effect=TimeoutError), \
             self.assertRaises(TimeoutError):
            cleanup(self.work, self.target, 123)
        self.assertTrue(self.work.exists())
        self.assertTrue((self.target/'settings.json').exists())

    def test_failed_result_after_wait_cannot_authorize_delete(self):
        def changed(*args):
            (self.work/'result.json').write_text(json.dumps({'ok': False}))
        with patch('update_cleanup.wait_worker', side_effect=changed), \
             patch('update_cleanup.shutil.rmtree') as remove, self.assertRaises(ValueError):
            cleanup(self.work, self.target, 123)
        remove.assert_not_called()

    def test_link_inside_workspace_blocks_recursive_deletion(self):
        with patch('update_cleanup.wait_worker'), \
             patch.object(Path, 'rglob', return_value=[Mock(is_symlink=Mock(return_value=True))]), \
             patch('update_cleanup.shutil.rmtree') as remove, self.assertRaises(ValueError):
            cleanup(self.work, self.target, 123)
        remove.assert_not_called()

    def test_only_validated_workspace_is_removed(self):
        with patch('update_cleanup.wait_worker'):
            self.assertEqual(cleanup(self.work, self.target, 123), 0)
        self.assertFalse(self.work.exists())
        self.assertEqual((self.target/'settings.json').read_text(), 'keep')

    def test_application_cleanup_mode_exits_without_gui_or_elevation(self):
        worker = subprocess.Popen([sys.executable, '-c', 'pass'],
                                  creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        worker.wait(timeout=10)
        result = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1]/'main.py'),
                                 '--cleanup-update', str(self.work), str(self.target), str(worker.pid)],
                                capture_output=True, timeout=15,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.work.exists())
        self.assertTrue((self.target/'settings.json').exists())

    def test_invalid_application_cleanup_mode_exits_with_failure_without_gui(self):
        result = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1]/'main.py'),
                                 '--cleanup-update', str(self.target), str(self.target), '123'],
                                capture_output=True, timeout=15,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.assertEqual(result.returncode, 1)
        self.assertTrue((self.target/'settings.json').exists())
