"""Build and verify the native app on Windows or macOS."""
from pathlib import Path
import json
import os
import platform
import plistlib
import shutil
import subprocess
import sys

from app_version import __version__


def main():
    root = Path(__file__).resolve().parent
    os.chdir(root)
    native = root/'dist' if sys.platform == 'darwin' else root/'dist'/f'native-{__version__}'
    args = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--windowed',
            '--hidden-import', 'matplotlib.backends.backend_pdf', '--hidden-import', 'cryptography',
            '--add-data', str(root/'update_config.json') + os.pathsep + '.',
            '--name', 'TEM-Studio', '--distpath', str(native), '--workpath', 'build', '--specpath', 'build']
    args += ['--onedir', '--osx-bundle-identifier', 'org.temstudio.app'] if sys.platform == 'darwin' else ['--onefile']
    subprocess.run(args + [str(root/'tem_studio.py')], check=True)
    dist = root/'dist'
    arch = {'amd64': 'x86_64', 'aarch64': 'arm64'}.get(platform.machine().lower(), platform.machine().lower())
    if sys.platform == 'darwin':
        app = dist/'TEM-Studio.app'
        plist = app/'Contents/Info.plist'
        info = plistlib.loads(plist.read_bytes())
        info['CFBundleShortVersionString'] = __version__
        info['CFBundleVersion'] = __version__
        plist.write_bytes(plistlib.dumps(info))
        subprocess.run(['codesign', '--force', '--deep', '--sign', '-', str(app)], check=True)
        executable = app/'Contents/MacOS/TEM-Studio'
        asset = dist/f'TEM-graph-tool-{__version__}-macos-{arch}.zip'
    elif sys.platform == 'win32':
        executable = native/'TEM-Studio.exe'
        asset = dist/f'TEM-graph-tool-{__version__}-windows-{arch}.exe'
    else:
        raise RuntimeError('Build on Windows or macOS')
    report = dist/'packaged-self-test.json'
    report.unlink(missing_ok=True)
    subprocess.run([str(executable), '--self-test', str(report)], check=True, timeout=180)
    result = json.loads(report.read_text(encoding='utf-8'))
    if not result.get('success') or not result.get('frozen'):
        raise RuntimeError(f'Packaged self-test failed: {result}')
    if sys.platform == 'darwin':
        subprocess.run(['ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', str(app), str(asset)], check=True)
    else:
        shutil.copy2(executable, asset)
    print(f'Built and verified {asset}')


if __name__ == '__main__':
    main()
