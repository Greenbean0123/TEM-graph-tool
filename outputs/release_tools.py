"""Publisher commands. Signing keys never belong in the repository."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import updater


def manifest(repo, assets, output, version):
    updater.version_tuple(version)
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo):
        raise ValueError('Use owner/repository')
    key = serialization.load_pem_private_key(os.environ['TEM_SIGNING_KEY'].encode(), password=None)
    public = base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
    if public != updater.bundled_config()['public_key']:
        raise ValueError('Signing key does not match the public key in the app')
    found = {}
    for path in Path(assets).rglob('*'):
        for platform, ext in [('windows-x86_64', 'exe'), ('macos-arm64', 'zip'), ('macos-x86_64', 'zip')]:
            if path.name == f'TEM-graph-tool-{version}-{platform}.{ext}':
                if platform in found:
                    raise ValueError(f'Duplicate release asset for {platform}')
                found[platform] = {'url': f'https://github.com/{repo}/releases/download/v{version}/{path.name}',
                                   'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'size': path.stat().st_size,
                                   'format': 'exe' if ext == 'exe' else 'app-zip'}
    if set(found) != {'windows-x86_64', 'macos-arm64', 'macos-x86_64'}:
        raise ValueError('Release must include Windows x64, Mac ARM and Mac Intel')
    payload = {'schema': 1, 'version': version, 'notes': f'TEM graph tool {version}', 'assets': found}
    envelope = {'payload': payload, 'signature': base64.b64encode(key.sign(updater.canonical(payload))).decode()}
    for platform in found:
        updater.verify_manifest(envelope, public, '0.0.0', platform)
    Path(output).write_text(json.dumps(envelope, indent=2), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--assets', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--version', required=True)
    args = parser.parse_args()
    manifest(args.repo, args.assets, args.output, args.version)
