import ctypes
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from shortcut_migration import StartupInfo, invoked_shortcut, migrate_shortcut
from windows_shortcuts import read_shortcut, write_shortcut

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == 'nt', 'Windows shortcut integration')
class ShortcutTest(unittest.TestCase):
    def setUp(self):
        (ROOT / 'build').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="EAB 링크'[] ", dir=ROOT / 'build')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.desktop = self.root / 'Desktop'
        self.desktop.mkdir()
        self.target = self.root / 'EAB.exe'
        self.target.touch()
        self.legacy = self.root / 'SecretShopBot-E7.exe'
        self.legacy.touch()

    def link(self, name, target=None, arguments='--admin "공백 있는 값"'):
        path = self.desktop / name
        write_shortcut(path, target or self.legacy, arguments, self.root)
        return path

    def properties(self, path):
        return read_shortcut(path)

    def test_replaces_only_invoked_link_and_preserves_arguments(self):
        old = self.link('기존 봇.lnk')
        other = self.link('또 다른 기존 봇.lnk')
        result = migrate_shortcut(self.target, [], old, desktop=self.desktop)
        self.assertTrue(result['removed_old'])
        self.assertFalse(old.exists())
        self.assertTrue(other.exists())
        new = Path(result['shortcut'])
        self.assertEqual(new, self.desktop / 'EAB.lnk')
        properties = self.properties(new)
        self.assertEqual(Path(properties['target']), self.target)
        self.assertEqual(properties['arguments'], '--admin "공백 있는 값"')
        self.assertEqual(Path(properties['directory']), self.root)

    def test_existing_correct_new_link_is_reused(self):
        old = self.link('기존.lnk')
        existing = self.link('EAB.lnk', self.target)
        before = existing.read_bytes()
        result = migrate_shortcut(self.target, [], old, desktop=self.desktop)
        self.assertEqual(Path(result['shortcut']), existing)
        self.assertEqual(existing.read_bytes(), before)
        self.assertFalse(old.exists())

    def test_migration_does_not_launch_a_shell_process(self):
        old = self.link('old.lnk')
        with patch('shortcut_migration.subprocess.run') as run, \
             patch('shortcut_migration.subprocess.Popen') as launch:
            result = migrate_shortcut(self.target, [], old, desktop=self.desktop)
        self.assertTrue(Path(result['shortcut']).is_file())
        run.assert_not_called()
        launch.assert_not_called()

    def test_changed_old_link_is_preserved_after_new_link_creation(self):
        old = self.link('old.lnk')
        write = __import__('shortcut_migration').write_shortcut
        def create_then_change(*args):
            write(*args)
            write(old, self.target, '--changed', self.root)
        with patch('shortcut_migration.write_shortcut', side_effect=create_then_change):
            result = migrate_shortcut(self.target, [], old, desktop=self.desktop)
        self.assertFalse(result['removed_old'])
        self.assertTrue(old.exists())

    def test_name_collision_does_not_overwrite_another_installation(self):
        unrelated = self.root / 'Other.exe'
        unrelated.touch()
        occupied = self.link('EAB.lnk', unrelated)
        before = occupied.read_bytes()
        old = self.link('old.lnk')
        result = migrate_shortcut(self.target, [], old, desktop=self.desktop)
        self.assertEqual(Path(result['shortcut']), self.desktop / 'EAB (2).lnk')
        self.assertEqual(occupied.read_bytes(), before)
        self.assertFalse(old.exists())

    def test_direct_legacy_execution_creates_new_link_without_deleting_others(self):
        old = self.link('old.lnk')
        result = migrate_shortcut(self.target, ['--admin'], desktop=self.desktop)
        self.assertFalse(result['removed_old'])
        self.assertTrue(old.exists())
        self.assertEqual(self.properties(Path(result['shortcut']))['arguments'], '--admin')

    def test_unrelated_invoked_link_is_not_deleted(self):
        unrelated = self.root / 'other.exe'
        unrelated.touch()
        old = self.link('unrelated.lnk', unrelated)
        before = old.read_bytes()
        result = migrate_shortcut(self.target, [], old, desktop=self.desktop)
        self.assertFalse(result['removed_old'])
        self.assertEqual(old.read_bytes(), before)

    def test_missing_app_and_failed_creation_keep_old_link(self):
        old = self.link('old.lnk')
        before = old.read_bytes()
        self.target.unlink()
        with self.assertRaises(RuntimeError):
            migrate_shortcut(self.target, [], old, desktop=self.desktop)
        self.assertEqual(old.read_bytes(), before)
        self.target.touch()
        with patch('shortcut_migration.write_shortcut', side_effect=RuntimeError('write failed')), \
                self.assertRaises(RuntimeError):
            migrate_shortcut(self.target, [], old, desktop=self.desktop)
        self.assertEqual(old.read_bytes(), before)

    def test_startup_metadata_accepts_only_link_flag_and_absolute_lnk(self):
        link = self.desktop / '실행한.lnk'
        references = []
        for flags, title, expected in ((0x800, str(link), link), (0x1000, str(link), None),
                                        (0x800, 'relative.lnk', None), (0x800, str(self.target), None)):
            def fill(info_pointer):
                info = ctypes.cast(info_pointer, ctypes.POINTER(StartupInfo)).contents
                info.dwFlags = flags
                info.lpTitle = title
                references.append(info)  # Keep the mock's LPWSTR allocation alive.
            kernel = Mock()
            kernel.GetStartupInfoW = Mock(side_effect=fill)
            with patch('shortcut_migration.ctypes.WinDLL', return_value=kernel):
                self.assertEqual(invoked_shortcut(), expected)
