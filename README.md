# TEM Graph tool

TEM Graph tool is a desktop application for clean TEM scale bars and particle-size distribution plots on Windows and macOS.

- Calibrate each TIFF independently from physical metadata or its original scale bar.
- Overlay a large, draggable scale bar with adjustable position, nm length, font size, thickness and black/white color.
- Import diameter CSV data and plot histograms with Gaussian fits, mean/std and N.
- Overlay a movable, resizable vector histogram on TEM; edit colors, opacity and label sizes.
- Export TIFF, PNG, SVG and PDF; preserve original input files.
- Light/dark themes, UI scaling and preview zoom; guide-line divider preview avoids live pane relayout.
- Scroll settings in small windows and save projects.
- Check GitHub Releases for signed updates and install with restart/rollback support.

Download standalone builds from [Releases](https://github.com/Greenbean0123/TEM-graph-tool/releases). Choose Windows x64, Mac Apple Silicon (arm64), or Mac Intel (x86_64).

## Run from source

```sh
python -m pip install -r outputs/requirements.txt
python outputs/tem_studio.py
```

Python with Tkinter is required. [User guide and CLI examples](outputs/README.md) · [Mac guide](outputs/README-Mac.md) · [Publishing updates](PUBLISHING.md).

Load sample generates synthetic demonstration data. No experimental images, measurements or private signing keys are included. Particle segmentation and automatic particle measurement are outside this application's scope.

## Build

Install `pyinstaller` plus outputs/requirements.txt, then run `python outputs/build_app.py` on Windows or macOS. The build runs packaged-app checks before creating an asset. Mac builds are ad-hoc signed, without Apple Developer ID notarization.

GitHub Actions builds Windows x64, Mac ARM and Mac Intel. A `v*` tag matching outputs/app_version.py publishes all three checked packages and a signed update manifest. See PUBLISHING.md for signing-key setup.

MIT license. Updater components are adapted from XRD Plotter by Greenbean0123 under the same license.
