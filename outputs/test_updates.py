"""Tests use temporary installs and test-only keys; no real app is replaced."""
from pathlib import Path
import base64
import hashlib
import io
import json
import os
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import updater
import update_installer
import update_cleanup
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.private = Ed25519PrivateKey.generate()
        self.public = base64.b64encode(self.private.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
        self.bytes = b'test package data'
        self.payload = {'schema': 1, 'version': '0.0.3', 'notes': 'Test release', 'assets': {
            'windows-x86_64': {'url': 'https://example.test/app.exe', 'size': len(self.bytes),
              'sha256': hashlib.sha256(self.bytes).hexdigest(), 'format': 'exe'}}}

    def signed(self):
        return {'payload': self.payload, 'signature': base64.b64encode(
            self.private.sign(updater.canonical(self.payload))).decode()}

    def release(self):
        return updater.verify_manifest(self.signed(), self.public, '0.0.2', 'windows-x86_64')

    def test_signed_update_and_numeric_versions(self):
        self.assertEqual(self.release()['version'], '0.0.3')
        self.assertIsNone(updater.verify_manifest(self.signed(), self.public, '0.0.3', 'windows-x86_64'))
        self.assertIsNone(updater.verify_manifest(self.signed(), self.public, '0.0.4', 'windows-x86_64'))
        self.assertGreater(updater.version_tuple('0.0.10'), updater.version_tuple('0.0.9'))

    def test_modified_manifest_and_wrong_key_are_rejected(self):
        envelope = self.signed()
        envelope['payload']['assets']['windows-x86_64']['url'] = 'https://other.test/malware.exe'
        with self.assertRaisesRegex(ValueError, 'signature'):
            updater.verify_manifest(envelope, self.public, '0.0.2', 'windows-x86_64')
        with self.assertRaises(ValueError):
            updater.verify_manifest(self.signed(), base64.b64encode(b'x' * 32).decode(), '0.0.2', 'windows-x86_64')

    def test_wrong_architecture_and_insecure_urls(self):
        with self.assertRaisesRegex(ValueError, 'does not include'):
            updater.verify_manifest(self.signed(), self.public, '0.0.2', 'macos-arm64')
        for url in ('http://example.test/app', 'file:///tmp/app', 'https://name:secret@example.test/app'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                updater.require_https(url)

    def test_download_checks_content_before_installing(self):
        with patch.object(updater, 'data_directory', return_value=self.root), patch.object(
                updater, 'open_https', return_value=io.BytesIO(self.bytes)):
            file = updater.download(self.release())
        self.assertEqual(file.read_bytes(), self.bytes)
        for bad_bytes in (b'wrong data', b'x' * (len(self.bytes) + 1)):
            with self.subTest(length=len(bad_bytes)), patch.object(updater, 'data_directory', return_value=self.root), patch.object(
                    updater, 'open_https', return_value=io.BytesIO(bad_bytes)), self.assertRaises(ValueError):
                updater.download(self.release())
        self.assertFalse(list(self.root.rglob('*.partial')))

    def test_no_server_is_explicit_and_network_free(self):
        with patch.object(updater, 'open_https') as network:
            with self.assertRaisesRegex(ValueError, 'No update server'):
                updater.check('0.0.2', {'manifest_url': '', 'public_key': self.public})
            network.assert_not_called()

    def test_zip_traversal_and_escaping_links(self):
        for filename in ('../bad', '/tmp/bad', 'TEM-Studio.app/../../bad', 'Other.app/a'):
            package = self.root / 'bad.zip'
            with zipfile.ZipFile(package, 'w') as archive:
                archive.writestr(filename, b'bad')
            with self.subTest(filename=filename), self.assertRaises(ValueError):
                update_installer.validate_zip(package)
        package = self.root / 'symlink.zip'
        with zipfile.ZipFile(package, 'w') as archive:
            info = zipfile.ZipInfo('TEM-Studio.app/link')
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, '../outside')
        with self.assertRaises(ValueError):
            update_installer.validate_zip(package)

    def test_mac_framework_relative_symlinks_are_allowed(self):
        package = self.root / 'framework.zip'
        with zipfile.ZipFile(package, 'w') as archive:
            info = zipfile.ZipInfo('TEM-Studio.app/Contents/Frameworks/Test.framework/Test')
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, 'Versions/Current/Test')
        update_installer.validate_zip(package)

    def test_symlink_ancestor_cannot_hide_an_escape(self):
        package = self.root / 'symlink-chain.zip'
        with zipfile.ZipFile(package, 'w') as archive:
            for name, target in [('TEM-Studio.app/dir', '.'),
                                 ('TEM-Studio.app/dir/link', '../outside')]:
                info = zipfile.ZipInfo(name)
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(info, target)
        with self.assertRaises(ValueError):
            update_installer.validate_zip(package)

    def test_successful_transaction_keeps_backup(self):
        target, staged, health = [self.root / name for name in ('app.exe', 'new.exe', 'ready')]
        target.write_text('old')
        staged.write_text('new')
        def launch(path, marker=None):
            marker.write_text('ready')
            return None
        backup = update_installer.replace_and_restart(target, staged, health, launch_app=launch, timeout=1)
        self.assertEqual(target.read_text(), 'new')
        self.assertEqual(backup.read_text(), 'old')

    def test_failed_startup_rolls_back_and_reopens_old_app(self):
        target, staged, health = [self.root / name for name in ('app.exe', 'new.exe', 'ready')]
        target.write_text('old')
        staged.write_text('broken new')
        launched = []
        class Failed:
            def poll(self):
                return 1
        def launch(path, marker=None):
            launched.append(path.read_text())
            return Failed()
        with self.assertRaisesRegex(RuntimeError, 'exited'):
            update_installer.replace_and_restart(target, staged, health, launch_app=launch, timeout=1)
        self.assertEqual(target.read_text(), 'old')
        self.assertEqual(launched, ['broken new', 'old'])

    def test_current_process_is_detected(self):
        self.assertTrue(update_installer.process_alive(os.getpid()))
        self.assertFalse(update_installer.process_alive(0))

    def cleanup_fixture(self):
        import time
        data = self.root/'data'
        directory = data/'updates'/('a'*32)
        directory.mkdir(parents=True)
        target = self.root/'TEM graphic tool.app'
        target.mkdir()
        (target/'version').write_text('new')
        backup = self.root/'TEM graphic tool.previous-1234abcd.app'
        backup.mkdir()
        (backup/'version').write_text('old')
        health = directory/'new-app-ready'
        health.write_text('ready')
        (directory/'job.json').write_text(json.dumps({'target': str(target), 'health': str(health)}))
        result = directory/'result.json'
        result.write_text(json.dumps({'success': True, 'backup': str(backup)}))
        os.utime(result, (time.time()-10, time.time()-10))
        (directory/'package.zip').write_text('download')
        (directory/'helper').mkdir()
        (directory/'helper'/'old-program').write_text('helper')
        return data, directory, target, backup

    def test_cleanup_removes_successful_old_app_and_temporary_package(self):
        data, directory, target, backup = self.cleanup_fixture()
        manual = self.root/'downloaded-installer.dmg'
        manual.write_text('user download')
        with patch.object(updater, 'data_directory', return_value=data):
            self.assertTrue(update_cleanup.cleanup(directory, target))
        self.assertFalse(backup.exists())
        self.assertFalse(directory.exists())
        self.assertEqual((target/'version').read_text(), 'new')
        self.assertTrue(manual.exists())

    def test_cleanup_keeps_backup_until_new_app_is_ready(self):
        data, directory, target, backup = self.cleanup_fixture()
        (directory/'new-app-ready').unlink()
        with patch.object(updater, 'data_directory', return_value=data):
            self.assertFalse(update_cleanup.cleanup(directory, target))
        self.assertTrue(backup.exists())
        self.assertTrue((directory/'package.zip').exists())

    def test_cleanup_refuses_unrelated_backup_path(self):
        data, directory, target, backup = self.cleanup_fixture()
        result = directory/'result.json'
        result.write_text(json.dumps({'success': True, 'backup': str(target)}))
        os.utime(result, (1, 1))
        with patch.object(updater, 'data_directory', return_value=data):
            self.assertFalse(update_cleanup.cleanup(directory, target))
        self.assertTrue(target.exists())
        self.assertTrue(backup.exists())


if __name__ == '__main__':
    unittest.main()
