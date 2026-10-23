import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

import legacy_launcher

ROOT = Path(__file__).resolve().parents[1]


class LauncherTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='EAB 연결 ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'EAB.exe').touch()
        migrator = patch('legacy_launcher.migrate_shortcut', return_value={'shortcut': 'EAB.lnk'})
        self.migrate = migrator.start()
        self.addCleanup(migrator.stop)
        invoked = patch('legacy_launcher.invoked_shortcut', return_value=self.root / 'old.lnk')
        invoked.start()
        self.addCleanup(invoked.stop)

    def test_shortcut_starts_eab_forwards_arguments_and_exits(self):
        args = ['--admin', '공백 포함 인자', 'quote"here']
        child = Mock()
        with patch('legacy_launcher.subprocess.Popen', return_value=child) as start, \
                patch('legacy_launcher.protect_update_process_tree') as protect:
            self.assertEqual(legacy_launcher.launch(self.root, args), 0)
        self.assertEqual(start.call_args.args[0], [str(self.root / 'EAB.exe'), *args])
        self.assertEqual(start.call_args.kwargs['cwd'], str(self.root))
        self.assertEqual(start.call_args.kwargs['env']['PYINSTALLER_RESET_ENVIRONMENT'], '1')
        child.wait.assert_not_called()
        protect.assert_not_called()
        self.migrate.assert_called_once_with(self.root / 'EAB.exe', args, self.root / 'old.lnk')

    def test_bridge_update_waits_for_child_instead_of_failing_startup_check(self):
        child = Mock(wait=Mock(return_value=17))
        order = []
        with patch('legacy_launcher.protect_update_process_tree', side_effect=lambda: order.append('protect')), \
                patch('legacy_launcher.subprocess.Popen', side_effect=lambda *a, **k: (order.append('launch'), child)[1]):
            self.assertEqual(legacy_launcher.launch(self.root, ['--update-ready', 'app-ready']), 17)
        self.assertEqual(order, ['protect', 'launch'])
        child.wait.assert_called_once()
        self.migrate.assert_not_called()

    def test_missing_eab_does_not_run_a_different_program(self):
        (self.root / 'EAB.exe').unlink()
        with patch('legacy_launcher.subprocess.Popen') as start:
            with self.assertRaises(FileNotFoundError):
                legacy_launcher.launch(self.root, [])
        start.assert_not_called()
        self.migrate.assert_not_called()

    def test_failed_app_launch_does_not_replace_shortcuts(self):
        with patch('legacy_launcher.subprocess.Popen', side_effect=OSError('blocked')):
            with self.assertRaises(OSError):
                legacy_launcher.launch(self.root, [])
        self.migrate.assert_not_called()

    def test_failed_shortcut_migration_does_not_prevent_app_launch(self):
        self.migrate.side_effect = PermissionError('read-only shortcut')
        with patch('legacy_launcher.subprocess.Popen') as start:
            self.assertEqual(legacy_launcher.launch(self.root, []), 0)
        start.assert_called_once()

    @unittest.skipUnless(os.name == 'nt', 'Windows job object integration')
    def test_update_launcher_termination_also_stops_child(self):
        marker = self.root / 'child.json'
        script = (
            'import json,subprocess,sys,time; '
            'from pathlib import Path; '
            'from legacy_launcher import protect_update_process_tree; '
            'job=protect_update_process_tree(); '
            'child=subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"]); '
            'Path(sys.argv[1]).write_text(json.dumps(child.pid)); time.sleep(60)'
        )
        parent = subprocess.Popen([sys.executable, '-c', script, str(marker)], cwd=ROOT,
                                  creationflags=subprocess.CREATE_NO_WINDOW)
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = None
        try:
            deadline = time.monotonic() + 10
            while not marker.exists() and parent.poll() is None and time.monotonic() < deadline:
                time.sleep(.05)
            self.assertTrue(marker.exists(), f'Job helper exited: {parent.poll()}')
            handle = kernel.OpenProcess(0x00100000, False, json.loads(marker.read_text()))
            self.assertTrue(handle)
            self.assertEqual(kernel.WaitForSingleObject(handle, 0), 258)  # WAIT_TIMEOUT
            parent.terminate()
            parent.wait(timeout=10)
            self.assertEqual(kernel.WaitForSingleObject(handle, 10000), 0)
        finally:
            if parent.poll() is None:
                parent.terminate()
                parent.wait(timeout=10)
            if handle:
                kernel.CloseHandle(handle)
