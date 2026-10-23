import unittest
from unittest.mock import patch

from src import auto_update, remote_script, release_checker
from src.app_identity import RELEASE_REPOSITORY, SUPPORTED_RELEASE_REPOSITORIES
from src.app_updater import release_assets
from src.release_checker import ReleaseInfo


class ReleaseAddressTest(unittest.TestCase):
    def test_defaults_query_only_new_repository(self):
        self.assertEqual(RELEASE_REPOSITORY, 'pelierze/EAB')
        self.assertEqual(SUPPORTED_RELEASE_REPOSITORIES, ('pelierze/EAB',))
        url = 'https://api.github.com/repos/pelierze/EAB/releases/latest'
        self.assertEqual(release_checker.RELEASE_API_URLS, (url,))
        with patch('src.release_checker._fetch_release_at', return_value=ReleaseInfo('v1.5.20', '', '')) as fetch:
            self.assertEqual(release_checker.fetch_latest_release().version, 'v1.5.20')
        fetch.assert_called_once_with(url)

    def test_failure_does_not_try_old_repository(self):
        with patch('src.release_checker._fetch_release_at', side_effect=OSError('offline')) as fetch:
            self.assertIsNone(release_checker.get_available_update('1.5.19'))
        fetch.assert_called_once_with(release_checker.DEFAULT_RELEASE_API_URL)

    def test_non_stable_default_release_is_rejected(self):
        with patch('src.release_checker._fetch_release_at', return_value=ReleaseInfo('v99.0.0-rc.1', '', '')):
            with self.assertRaises(ValueError):
                release_checker.fetch_latest_release()

    def test_explicit_custom_endpoint_keeps_its_behavior(self):
        url = 'https://example.test/releases/latest'
        with patch('src.release_checker._fetch_release_at', return_value=ReleaseInfo('v1.5.20', url, '')) as fetch:
            self.assertEqual(release_checker.fetch_latest_release(url).url, url)
        fetch.assert_called_once_with(url)


class DownloadAddressTest(unittest.TestCase):
    def release(self, repo, package='EAB'):
        name = f'{package}-v1.5.20.zip'
        assets = tuple({'name': asset, 'browser_download_url':
                        f'https://github.com/{repo}/releases/download/v1.5.20/{asset}'}
                       for asset in (name, name + '.sha256.txt'))
        return ReleaseInfo('v1.5.20', '', '', assets=assets)

    def test_supported_filenames_on_new_repository(self):
        for package in ('SecretShopBot-E7', 'EAB'):
            self.assertEqual(release_assets(self.release('pelierze/EAB', package))[0], f'{package}-v1.5.20.zip')

    def test_old_repository_no_longer_allowed_for_downloads(self):
        with self.assertRaises(ValueError):
            release_assets(self.release('pelierze/SecretShopBot-E7'))

    def test_other_repositories_and_wrong_versions_rejected(self):
        release = self.release('pelierze/EAB')
        original = release.assets[0]['browser_download_url']
        for url in (original.replace('pelierze/EAB', 'someone/EAB'),
                    original.replace('pelierze/EAB', 'pelierze/EAB-other'),
                    original.replace('github.com', 'github.com.evil.test'),
                    original.replace('/v1.5.20/', '/v1.5.19/'),
                    original.replace('/v1.5.20/', '/v1.5.20/extra/'),
                    original + '?redirect=elsewhere'):
            with self.subTest(url=url):
                release.assets[0]['browser_download_url'] = url
                with self.assertRaises(ValueError):
                    release_assets(release)


class RemoteAddressTest(unittest.TestCase):
    def sources(self):
        return ((auto_update, auto_update.SettingsUpdater, auto_update.UPDATE_URLS),
                (remote_script, remote_script.RemoteScriptUpdater, remote_script.SCRIPT_URLS))

    def test_defaults_query_new_address_once(self):
        for module, cls, urls in self.sources():
            updater = cls()
            self.assertEqual(len(urls), 1)
            self.assertIn('/pelierze/EAB/master/', urls[0])
            with patch.object(module, 'fetch_json', return_value={'schema_version': 1}) as fetch, \
                    patch.object(updater, 'save_cache'):
                self.assertEqual(updater.load()[1], 'remote')
            fetch.assert_called_once_with(urls[0])

    def test_unavailable_new_address_uses_cache_bundled_or_defaults(self):
        for module, cls, urls in self.sources():
            for error in (OSError('offline'), ValueError('invalid JSON')):
                for fallback, data in (('cache', [{'schema_version': 1}]),
                                       ('bundled', [None, {'schema_version': 1}]),
                                       ('default', [None, None])):
                    updater = cls()
                    with self.subTest(module=module.__name__, fallback=fallback, error=error), \
                            patch.object(module, 'fetch_json', side_effect=error) as fetch, \
                            patch.object(module, 'read_json', side_effect=data):
                        self.assertEqual(updater.load()[1], fallback)
                    fetch.assert_called_once_with(urls[0])

    def test_invalid_schema_does_not_try_old_address(self):
        for module, cls, urls in self.sources():
            with patch.object(module, 'fetch_json', return_value={'schema_version': 99}) as fetch, \
                    patch.object(module, 'read_json', return_value=None):
                self.assertEqual(cls().load()[1], 'default')
            fetch.assert_called_once_with(urls[0])

    def test_custom_address_is_not_replaced(self):
        for module, cls, urls in self.sources():
            url = 'https://example.test/config.json'
            updater = cls(url)
            with patch.object(module, 'fetch_json', return_value={'schema_version': 1}) as fetch, \
                    patch.object(updater, 'save_cache'):
                self.assertEqual(updater.load()[1], 'remote')
            fetch.assert_called_once_with(url)
