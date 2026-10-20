"""Package an already verified Mac app into a drag-to-Applications DMG."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile

from app_version import APP_NAME, __version__


def run(*args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--app', type=Path)
    p.add_argument('--zip', type=Path)
    p.add_argument('--sha256')
    p.add_argument('--arch', required=True, choices=['arm64', 'x86_64'])
    p.add_argument('--output-dir', type=Path, default=Path(__file__).parent/'dist')
    args = p.parse_args()
    if sys.platform != 'darwin':
        p.error('DMGs must be built and verified on macOS')
    if bool(args.app) == bool(args.zip):
        p.error('Specify exactly one of --app or --zip')
    import dmgbuild
    from ds_store import DSStore
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    destination = out/f'TEM-graphic-tool-{__version__}-macos-{args.arch}.dmg'
    with tempfile.TemporaryDirectory(prefix='tem-dmg-') as temporary:
        work = Path(temporary)
        app = args.app.resolve() if args.app else None
        if args.zip:
            if not args.sha256 or hashlib.sha256(args.zip.read_bytes()).hexdigest() != args.sha256:
                raise ValueError('Release ZIP SHA256 mismatch')
            run('ditto', '-x', '-k', args.zip.resolve(), work/'unpacked')
            app = work/'unpacked'/'TEM-Studio.app'
        with (app/'Contents/Info.plist').open('rb') as stream:
            info = plistlib.load(stream)
        assert info['CFBundleIdentifier'] == 'org.temstudio.app'
        assert info['CFBundleShortVersionString'] == __version__
        assert info['CFBundleDisplayName'] == APP_NAME
        executable = Path('Contents/MacOS')/info['CFBundleExecutable']
        assert args.arch in subprocess.check_output(['lipo', '-archs', str(app/executable)], text=True).split()
        run('codesign', '--verify', '--deep', '--strict', app)
        icon = info['CFBundleIconFile']
        if not icon.endswith('.icns'):
            icon += '.icns'
        installed_name = APP_NAME+'.app'
        settings = dict(files=[(str(app), installed_name)], symlinks={'Applications': '/Applications'},
            icon=str(app/'Contents/Resources'/icon), background='builtin-arrow',
            window_rect=((100, 100), (640, 280)), default_view='icon-view',
            icon_locations={installed_name: (140, 120), 'Applications': (500, 120)},
            icon_size=96, text_size=14, grid_spacing=80, arrange_by=None,
            show_toolbar=False, show_sidebar=False, show_status_bar=False,
            show_tab_view=False, show_pathbar=False, format='UDZO', filesystem='HFS+')
        dmgbuild.build_dmg(str(destination), APP_NAME, settings=settings)
        run('hdiutil', 'verify', destination)
        mount = work/'mount'
        mount.mkdir()
        run('hdiutil', 'attach', '-readonly', '-nobrowse', '-mountpoint', mount, destination)
        try:
            assert (mount/'Applications').is_symlink()
            assert os.readlink(mount/'Applications') == '/Applications'
            mounted_app = mount/installed_name
            run('codesign', '--verify', '--deep', '--strict', mounted_app)
            with DSStore.open(str(mount/'.DS_Store'), 'r') as store:
                assert store[installed_name]['Iloc'] == (140, 120)
                assert store['Applications']['Iloc'] == (500, 120)
            # Simulate Finder's copy into an applications folder, then launch.
            copied = work/'installed'/installed_name
            copied.parent.mkdir()
            run('ditto', mounted_app, copied)
            run('codesign', '--verify', '--deep', '--strict', copied)
            report = out/f'dmg-{args.arch}-self-test.json'
            run(copied/executable, '--self-test', report, timeout=240)
            result = json.loads(report.read_text())
            assert result['success'] and result['frozen'] and result['application_name'] == APP_NAME
            result['dmg'] = dict(app_name=installed_name, architecture=args.arch,
                applications_shortcut='verified', finder_icon_layout='verified',
                installed_copy_launch='passed', sha256=hashlib.sha256(destination.read_bytes()).hexdigest())
            report.write_text(json.dumps(result, indent=2))
        finally:
            run('hdiutil', 'detach', mount)
    print('Built and verified', destination, flush=True)


if __name__ == '__main__':
    main()
