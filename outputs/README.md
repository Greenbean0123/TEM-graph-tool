# TEM graphic tool

A desktop tool for TEM scale-bar redrawing and diameter histograms with Gaussian fits. No particle detection or diameter extraction is performed.

## Desktop workflow

1. **Data & calibration**: Add TIFF images. Auto mode reads the original nm/µm text using the operating system's OCR and measures the bar independently for each image. Detected original length, pixel width and nm/pixel are filled into the left panel. **Original label unit** defaults to nm and also supports µm. Correct the number or unit manually when needed. If the OCR reads the number but not its unit, the selected unit is used and a verification message is displayed. Re-detect original scale bar retries recognition; manual label/width and nm/pixel remain available. Draw an erase box covering the original label and bar when needed.
2. **Scale bar**: Change nm length, black/white color, thickness, font size, corner and margin. Drag the new bar in the preview for custom positioning. X/Y are the top-left of the combined label and bar. The bar is overlaid directly on the image without expanding its canvas.
3. **Distribution**: Open CSV, select a named diameter column in nm, choose bins or bin width and Count/Frequency. Preview then Export current for PNG and optional PDF.
4. Export all TEM uses each image's independent calibration and appearance. Save/Open project preserves input paths and settings; input data must remain at those paths.

**Remove black footer** defaults to Yes: after reading the original scale, the separate black annotation strip is cropped off and the new scale is placed on the remaining microscopy image. This changes output height but preserves microscopy pixels and physical calibration. No/`--keep-original-footer` keeps the old strip. Images without a separate black footer are not automatically cropped; their original annotation is cleared locally with an erase box.

All four left tabs scroll vertically with the wheel/trackpad or scrollbar. Load sample generates a temporary **synthetic demonstration**, not experimental measurements.

## Command line

```sh
python -m pip install -r outputs/requirements.txt
python outputs/startup_launcher.py
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

Explicit physical metadata is preferred: OME PhysicalSizeX/Y, ImageJ units and XResolution, or JSON `nm_per_pixel`. Ordinary TIFF print resolution is ignored. Unsupported vendor-specific metadata needs manual calibration. Original-bar detection requires at least three repeated high-contrast horizontal scan lines; ambiguous layouts need manual measurement or a restricted search box. macOS uses the system Vision framework for local text recognition, with no cloud service or model download. Windows uses its built-in OCR when available. Split text observations such as `50` and `nm` are combined. Unclear/conflicting numbers are rejected; a single clear number with an unreadable unit uses the unit selected by the user (default nm). CLI equivalent: `--ocr-default-unit nm` or `um`.

New images default to the original detected nm length: a 50 nm original yields a 50 nm new bar, retaining its calibrated pixel width while increasing text size and line thickness. Users can change the new length afterward. When only physical metadata is available and no original nm label is known, a suitable neat value is selected for the image width. Original and newly drawn nm values are displayed separately. CLI users can opt into this behavior with `--match-original-bar`.

New pixel width is rounded from nm/calibration with error at most 0.5 px. Automatic nm choices are 10/20/50/100/200/500. Only single-page uint8 grayscale/RGB TIFF is supported; other formats are rejected rather than silently converted. Raw TIFFs are never overwritten. Derived `_scalebar.tif/.png` files may be replaced on repeated export to the same folder.

Gaussian MLE uses scipy.stats.norm.fit; std is population standard deviation (ddof=0), not sample standard deviation. The curve is scaled by N × bin width for Count or 100 × bin width for Frequency (%). Nonpositive/nonfinite values are rejected. Exports include PNG at ≥300 dpi, optional PDF, and JSON reports.

## Updates

The Updates tab checks signed manifests from the project's GitHub Releases, automatically at startup by default. Updates require confirmation before download, installation and restart. Downloads must match signed SHA256 and size. The detached installer keeps a backup and restores it if the new app does not become ready. Current image/settings state is saved outside the app and restored after restart. Source runs can check for updates; automatic replacement requires a bundled EXE or .app.

Release signing/publishing instructions are in ../PUBLISHING.md. Private keys must never be committed. User-specified update URLs still require the embedded publisher signing key.

After the updated app reports a successful startup and its installer exits, old program backups and temporary update packages/helpers are cleaned automatically. Interrupted cleanup is retried on later starts. Failed updates retain their recovery files. Manually downloaded installers, projects and experimental inputs are preserved.

## Build and test

Windows: `powershell -ExecutionPolicy Bypass -File outputs/Build-Windows.ps1`.

Mac: see README-Mac.md; run Build-Mac.command on the target architecture. Both use build_app.py, which runs the frozen app's self-test before producing a release asset.

```sh
python outputs/test_updates.py
python outputs/test_tem_studio.py
python outputs/tem_studio.py --self-test check.json
```

Checks cover updater signature/checksum handling, installation rollback, image-specific calibration, image pixel preservation, dragging, small-window scrolling and distribution PNG/PDF export.

## Local zoom inset (0.0.2 test)
Open **Inset zoom**, click **Select source region on image**, and drag a rectangle.
Drag the inset to move it; drag its yellow lower-right handle to resize it.
Width preserves the selected aspect ratio. X/Y, border thickness, black/white color,
connector line and inset scale-bar length are editable in the left panel.
A blank inset scale-bar length selects a readable physical length automatically.
The inset samples the cleaned original image before any new annotation is drawn.
The independent nm/pixel calibration updates when the inset size changes.
Export current / Export all include the inset in both PNG and TIFF. Original files
remain unchanged. Each image stores its own inset settings in saved projects.

CLI example (coordinates refer to the image after footer removal):
```
python tem_scalebar_distribution.py --tiff sample.tif --nm-per-pixel 0.5 --inset-roi 100,100,300,300 --inset-width 600 --inset-x 1000 --inset-y 50 --inset-color white --inset-border 4 --output-dir results
```

The source region and inset are joined by two edge-to-edge connector lines.
Connector thickness (1–30 px) and black/white color are independently configurable
from the inset frame, including CLI --inset-connector-width and --inset-connector-color.
Inset scale labels and bars are drawn directly on the microscopy without a background block.

### Zoom scale visibility
In **Inset zoom**, set **Show inset scale bar** to **Yes** (default) or **No**.
This controls only the inset label and line. It is saved per image and in projects,
used in both preview and exported TIFF/PNG, and leaves the main scale bar setting unchanged.
CLI: add `--inset-no-scalebar` to hide the inset scale bar.
