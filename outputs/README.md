# TEM Studio / TEM graph tool

A desktop tool for TEM scale-bar redrawing and diameter histograms with Gaussian fits. No particle detection or diameter extraction is performed.

## Desktop workflow

1. **Data & calibration**: Add TIFF images. Read the original nm label separately for each image. Use automatic bar-width measurement in a separate uniform footer, drag between the original bar endpoints, or enter nm/pixel. Draw an erase box covering the original label and bar when needed.
2. **Scale bar**: Change nm length, black/white color, thickness, font size, corner and margin. Drag the new bar in the preview for custom positioning. X/Y are the top-left of the combined label and bar. The bar is overlaid directly on the image without expanding its canvas.
3. **Distribution**: Open CSV, select a named diameter column in nm, choose bins or bin width and Count/Frequency. Preview then Export current for PNG and optional PDF.
4. Export all TEM uses each image's independent calibration and appearance. Save/Open project preserves input paths and settings; input data must remain at those paths.

All four left tabs scroll vertically with the wheel/trackpad or scrollbar. Load sample generates a temporary **synthetic demonstration**, not experimental measurements.

## Command line

```sh
python -m pip install -r outputs/requirements.txt
python outputs/tem_studio.py
python outputs/tem_scalebar_distribution.py --tiff sample.tif --csv diameters.csv --column diameter_nm --measure-original-bar --original-bar-nm 200 --bar-nm 500 --font-size 64 --thickness 18 --margin 110 --pdf
```

Use `--help` for all options. Alternatives: `--nm-per-pixel 0.8`, or `--original-bar-nm 200 --original-bar-px 251`. Numbers in this command are examples, not a calibration for arbitrary images. Every image needs its own reliable calibration.

`--image-config images.json` accepts a mapping from exact image filename to underscore-named per-image options, such as:

```json
{
  "sample.tif": {
    "original_bar_nm": 200,
    "measure_original_bar": true,
    "erase_box": [0, 2048, 2048, 2115]
  }
}
```

Example coordinates must be adapted to the actual image. `--measure-box x0,y0,x1,y1` limits original-bar measurement. `--erase-box` specifies the region to cover; right/bottom boundaries are exclusive. Without an explicit erase box, a separate uniform footer is detected, otherwise a configurable corner rectangle is used. Verify the preview to avoid covering microscopy content. Background defaults to the erased region's median, or can be set to 0/255.

## Calibration and statistics

Explicit physical metadata is preferred: OME PhysicalSizeX/Y, ImageJ units and XResolution, or JSON `nm_per_pixel`. Ordinary TIFF print resolution is ignored. Unsupported vendor-specific metadata needs manual calibration. Original-bar detection requires at least three repeated high-contrast horizontal scan lines; ambiguous layouts need manual measurement or a restricted search box. It does not read nm labels using OCR.

New pixel width is rounded from nm/calibration with error at most 0.5 px. Automatic nm choices are 10/20/50/100/200/500. Only single-page uint8 grayscale/RGB TIFF is supported; other formats are rejected rather than silently converted. Raw TIFFs are never overwritten. Derived `_scalebar.tif/.png` files may be replaced on repeated export to the same folder.

Gaussian MLE uses scipy.stats.norm.fit; std is population standard deviation (ddof=0), not sample standard deviation. The curve is scaled by N × bin width for Count or 100 × bin width for Frequency (%). Nonpositive/nonfinite values are rejected. Exports include PNG at ≥300 dpi, optional PDF, and JSON reports.

## Updates

The Updates tab checks signed manifests from the project's GitHub Releases, automatically at startup by default. Updates require confirmation before download, installation and restart. Downloads must match signed SHA256 and size. The detached installer keeps a backup and restores it if the new app does not become ready. Current image/settings state is saved outside the app and restored after restart. Source runs can check for updates; automatic replacement requires a bundled EXE or .app.

Release signing/publishing instructions are in ../PUBLISHING.md. Private keys must never be committed. User-specified update URLs still require the embedded publisher signing key.

## Build and test

Windows: `powershell -ExecutionPolicy Bypass -File outputs/Build-Windows.ps1`.

Mac: see README-Mac.md; run Build-Mac.command on the target architecture. Both use build_app.py, which runs the frozen app's self-test before producing a release asset.

```sh
python outputs/test_updates.py
python outputs/test_tem_studio.py
python outputs/tem_studio.py --self-test check.json
```

Checks cover updater signature/checksum handling, installation rollback, image-specific calibration, image pixel preservation, dragging, small-window scrolling and distribution PNG/PDF export.
