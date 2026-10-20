import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
import zipfile

from build_support.release_assets import RUNTIME_FILES, used_images, validate_package
from build_support.release_packages import create_packages
from src.app_identity import resolve_app_executable
from src.app_updater import extract_verified, release_assets
from src.release_checker import ReleaseInfo
from updater_main import apply_update

ROOT = Path(__file__).resolve().parents[1]


class EabReleaseTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.build = self.root / 'build'
        self.build.mkdir()
        for name in ('EAB.exe', 'EAB-Updater.exe', 'SecretShopBot-E7.exe'):
            (self.build / name).write_bytes(name.encode())
        for name in (*RUNTIME_FILES, *used_images(ROOT), 'update_config.json',
                     'remote_script.json', 'src/chaos/recruitment_layout.json',
                     'src/chaos/node_layout.json', 'python312.dll'):
            path = self.build / '_internal' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
        self.output = self.root / 'release'

    def packages(self, version='v1.5.20'):
        return create_packages(self.build, self.output, version)

    def extract(self, name, destination):
        archive = self.output / (name + '.zip')
        return extract_verified(archive, archive.with_name(archive.name + '.sha256.txt'), destination)

    def test_eab_archive_has_correct_root_checksum_and_shortcut_launcher(self):
        artifacts = self.packages()
        self.assertEqual(len(artifacts), 2)
        package = self.extract('EAB-v1.5.20', self.root / 'EAB')
        validate_package(package, profile='eab')
        eab = self.root / 'EAB/EAB-v1.5.20'
        self.assertEqual((eab / 'SecretShopBot-E7.exe').read_bytes(), b'SecretShopBot-E7.exe')
        self.assertEqual({p.name for p in self.output.iterdir()},
                         {'EAB-v1.5.20.zip', 'EAB-v1.5.20.zip.sha256.txt'})
        for archive in self.output.glob('*.zip'):
            with zipfile.ZipFile(archive) as z:
                self.assertEqual({p.split('/')[0] for p in z.namelist()}, {archive.stem})

    def test_current_client_selects_eab_without_legacy_archive(self):
        artifacts = self.packages()
        release = ReleaseInfo('v1.5.20', '', '', assets=tuple(
            {'name': path.name, 'browser_download_url':
             'https://github.com/pelierze/SecretShopBot-E7/releases/download/v1.5.20/' + path.name}
            for path in artifacts))
        self.assertEqual(release_assets(release)[0], 'EAB-v1.5.20.zip')

    def test_existing_artifacts_are_not_overwritten(self):
        artifacts = self.packages()
        before = {p.name: hashlib.sha256(p.read_bytes()).digest() for p in artifacts}
        (self.build / 'EAB.exe').write_bytes(b'changed')
        with self.assertRaises(FileExistsError):
            self.packages()
        self.assertEqual(before, {p.name: hashlib.sha256(p.read_bytes()).digest() for p in artifacts})

    def test_incomplete_eab_pair_is_rejected(self):
        artifacts = self.packages()
        release = ReleaseInfo('v1.5.20', '', '', assets=tuple(
            {'name': path.name, 'browser_download_url':
             'https://github.com/pelierze/SecretShopBot-E7/releases/download/v1.5.20/' + path.name}
            for path in artifacts if path.name != 'EAB-v1.5.20.zip.sha256.txt'))
        with self.assertRaises(ValueError):
            release_assets(release)

    def test_invalid_build_and_version_publish_nothing(self):
        with self.assertRaises(ValueError):
            self.packages('../escape')
        (self.build / 'extra.txt').touch()
        with self.assertRaises(ValueError):
            self.packages()
        self.assertFalse(self.output.exists())

    def test_duplicate_app_instead_of_launcher_is_rejected(self):
        self.packages()
        eab = self.extract('EAB-v1.5.20', self.root / 'unpacked')
        (eab / 'SecretShopBot-E7.exe').write_bytes((eab / 'EAB.exe').read_bytes())
        with self.assertRaisesRegex(ValueError, 'differ'):
            validate_package(eab, profile='eab')

    def test_updates_preserve_shortcut_settings_and_recovery(self):
        self.packages()
        target = self.root / 'installed'
        target.mkdir()
        (target / 'SecretShopBot-E7.exe').write_bytes(b'old')
        (target / 'SecretShopBot-Updater.exe').write_bytes(b'old-helper')
        (target / '_internal').mkdir()
        (target / 'settings.json').write_text('user')
        launcher = Mock(return_value=Mock(poll=Mock(return_value=None)))
        for attempt in range(2):
            package = self.extract('EAB-v1.5.20', self.root / f'payload{attempt}')
            work = self.root / f'work{attempt}'
            work.mkdir()
            apply_update(target, package, work, launcher, Mock())
            self.assertEqual(resolve_app_executable(target).name, 'EAB.exe')
            self.assertEqual((target / 'SecretShopBot-E7.exe').read_bytes(), b'SecretShopBot-E7.exe')
            self.assertEqual((target / 'settings.json').read_text(), 'user')
        original = (target / 'EAB.exe').read_bytes()
        original_launcher = (target / 'SecretShopBot-E7.exe').read_bytes()
        package = self.extract('EAB-v1.5.20', self.root / 'failed-payload')
        (package / 'EAB.exe').write_bytes(b'bad')
        (package / 'SecretShopBot-E7.exe').write_bytes(b'bad')
        work = self.root / 'failed-work'
        work.mkdir()
        with self.assertRaisesRegex(RuntimeError, '복구'):
            apply_update(target, package, work, launcher, Mock(side_effect=RuntimeError('failed')))
        self.assertEqual((target / 'EAB.exe').read_bytes(), original)
        self.assertEqual((target / 'SecretShopBot-E7.exe').read_bytes(), original_launcher)
        self.assertEqual((target / 'settings.json').read_text(), 'user')
