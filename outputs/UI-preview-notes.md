# UI and overlay notes (0.0.4)

- Top right: Light / Dark theme and UI size, from 80% to 200%. Preferences are saved locally.
- Preview: + / − zoom, Fit to reset, right-drag (or middle-drag) to pan. Scale bar dragging and measurements still use original image pixels.
- Settings panels scroll vertically and horizontally, including when the interface is enlarged.
- The preview header shows the current TIFF filename, or the CSV filename when displaying a size distribution.
- TIFF calibration and scale bar settings are independent for each image. The diameter CSV is currently a shared selection, not a per-TIFF association. Select the appropriate CSV before previewing or exporting a distribution.
- Theme and preview zoom do not change exported figures. Default scale bar thickness is 36 px and font size is 128 px; saved image settings take priority.
- Preview redraws reuse the canvas image layer and skip unchanged renders to reduce flashes during tab switches.
- Divider dragging shows only a lightweight guide line, without relaying out either pane. Release applies the split once, displays a cached low-resolution preview, then loads the clear image after a short pause. RGB conversion and chart panels are cached.
- Size → Distribution on TEM enables the selected CSV as a movable, resizable chart overlay (white or transparent background). Export SVG/PDF for true vector bars, curves and text over the raster TEM. Standalone distribution SVG is also available.
- The compact overlay defaults to red bars / blue curve, lower-right placement (avoiding the main scale bar where possible), and a white plot area with transparent margins (`plot only`). Set X/Y for custom placement. Histogram and curve colors have color pickers or hex entry; bar, curve and background opacity range from 0 (transparent) to 1 (opaque). Color/opacity also apply to standalone distribution exports. `density` normalizes histogram area to 1.
- Overlay axis labels, tick labels and mean/std/N annotations have independent font sizes. Sizes are points in the chart template and scale with panel width, consistently for preview, PNG/TIFF and vector exports. The bottom progress bar reports real processing stages (read TEM, calibrate, prepare chart, composite, preview/export), rather than elapsed-time estimates.

Run the source with `python outputs/tem_studio.py`. Release packages are built and tested natively for Windows x64, Mac Apple Silicon and Mac Intel. Older local previews in `outputs/dist/local-ui-preview/` are development snapshots; use the release download for the current version.
