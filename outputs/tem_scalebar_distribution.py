"""TEM annotation and diameter histograms; see --help and README.md."""
import argparse
import copy
import csv
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
import tifffile
from PIL import Image, ImageDraw, ImageFont
from scipy.stats import norm
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
# Explicit import also makes the optional PDF writer visible to PyInstaller.
from matplotlib.backends import backend_pdf  # noqa: F401


def positive(s):
    v = float(s)
    if not math.isfinite(v) or v <= 0:
        raise argparse.ArgumentTypeError('Must be finite and positive')
    return v


def calibration(tf):
    """Use explicit physical units only; ordinary TIFF print resolution is ignored."""
    units = {'nm': 1, 'um': 1000, 'µm': 1000, 'μm': 1000, 'mm': 1e6, 'm': 1e9}
    if tf.ome_metadata:
        root = ET.fromstring(tf.ome_metadata)
        p = root.find('.//{*}Pixels')
        if p is not None and p.get('PhysicalSizeX'):
            ux = p.get('PhysicalSizeXUnit', 'µm')
            uy = p.get('PhysicalSizeYUnit', ux)
            if ux in units and uy in units:
                x = float(p.get('PhysicalSizeX')) * units[ux]
                y = float(p.get('PhysicalSizeY', p.get('PhysicalSizeX'))) * units[uy]
                if not np.isclose(x, y, rtol=0.001):
                    raise ValueError('Anisotropic pixels: resample before drawing a scale bar')
                return x, 'OME PhysicalSizeX'
    md = tf.imagej_metadata or {}
    unit = str(md.get('unit', '')).lower()
    tag = tf.pages[0].tags.get('XResolution')
    if unit in units and tag:
        num, den = tag.value
        return units[unit] * den / num, 'ImageJ unit / XResolution'
    desc = tf.pages[0].description
    if desc:
        try:
            obj = json.loads(desc)
            if 'nm_per_pixel' in obj:
                return float(obj['nm_per_pixel']), 'JSON nm_per_pixel'
        except (ValueError, TypeError):
            pass
    return None, None


def rectangle(s):
    try:
        v = tuple(map(int, s.split(',')))
        if len(v) != 4 or v[2] <= v[0] or v[3] <= v[1]:
            raise ValueError()
        return v
    except ValueError:
        raise argparse.ArgumentTypeError('Use x0,y0,x1,y1 (exclusive right/bottom)')


def redraw(path, args, render_only=False):
    with tifffile.TiffFile(path) as tf:
        if len(tf.pages) != 1:
            raise ValueError('Only single-frame TIFF supported; export the desired frame first')
        a = tf.pages[0].asarray()
        scale, source = calibration(tf)
    if a.dtype != np.uint8 or a.ndim not in (2, 3) or (a.ndim == 3 and a.shape[2] != 3):
        raise ValueError('Use uint8 grayscale or RGB TIFF; other bit depths require explicit conversion')
    measured_pixels = None
    recognized_text = None
    label_reader = None
    if scale is None and args.measure_original_bar:
        gray = a if a.ndim == 2 else a.mean(axis=2)
        region = args.measure_box
        if region is None:
            for y in range(int(a.shape[0]*.85), a.shape[0]-4):
                level = gray[y, 0]
                if np.all(gray[y] == level) and np.all(gray[y:, :8] == level) and np.all(gray[y:, -8:] == level):
                    region = (0, y, a.shape[1], a.shape[0])
                    break
        if region is None:
            if args.erase_box:
                region = args.erase_box
            else:
                rw, rh = min(args.erase_width, a.shape[1]), min(args.erase_height, a.shape[0])
                rx = a.shape[1]-rw if 'right' in args.original_corner else 0
                ry = a.shape[0]-rh if 'bottom' in args.original_corner else 0
                region = (rx, ry, rx+rw, ry+rh)
        rx0, ry0, rx1, ry1 = region
        if not (0 <= rx0 < rx1 <= a.shape[1] and 0 <= ry0 < ry1 <= a.shape[0]):
            raise ValueError('Measurement region outside image')
        patch = gray[ry0:ry1, rx0:rx1]
        background = float(np.median(patch))
        # Measure repeated horizontal runs, requiring high contrast to the footer.
        mask = patch > background+100 if background < 128 else patch < background-100
        runs = []
        for row in mask:
            edges = np.diff(np.r_[False, row, False].astype(int))
            runs.extend((int(s), int(e)) for s, e in zip(np.where(edges == 1)[0], np.where(edges == -1)[0]) if e-s >= 30)
        if not runs:
            raise ValueError('No high-contrast bar detected in measurement region')
        candidates = {r: runs.count(r) for r in set(runs)}
        repeated = [r for r, count in candidates.items() if count >= 3]
        if not repeated:
            raise ValueError('No bar with >=3 identical scan lines; provide manual pixel measurement')
        best = max(repeated, key=lambda r: r[1]-r[0])
        measured_pixels = best[1]-best[0]
        if not args.original_bar_nm:
            from scale_ocr import read_scale_label
            args.original_bar_nm, recognized_text, label_reader = read_scale_label(a, region, default_unit=getattr(args, 'ocr_default_unit', 'nm'))
        args.original_bar_px = measured_pixels
    if scale is None:
        scale = args.nm_per_pixel
        source = 'CLI nm_per_pixel'
        if scale is None and args.original_bar_nm and args.original_bar_px:
            scale = args.original_bar_nm / args.original_bar_px
            source = 'original_bar_nm / measured_pixels' if measured_pixels else 'CLI original_bar_nm / original_bar_px'
    if scale is None or not math.isfinite(scale) or scale <= 0:
        raise ValueError(f'{path.name}: no valid physical calibration; supply --nm-per-pixel or both --original-bar-*')
    im = Image.fromarray(a)
    w, h = im.size
    gray = a if a.ndim == 2 else a.mean(axis=2)
    # A separate footer is safe to clear automatically only when a flat
    # full-width separator and uniform side margins delimit it.
    roi = args.erase_box
    footer = None
    for y in range(int(h * .85), h - 4):
        level = gray[y, 0]
        if np.all(gray[y] == level) and np.all(gray[y:, :8] == level) and np.all(gray[y:, -8:] == level):
            footer = (0, y, w, h)
            break
    if roi is None:
        roi = footer
    if roi is None:
        rw, rh = args.erase_width, args.erase_height
        x = w - rw if 'right' in args.original_corner else 0
        y = h - rh if 'bottom' in args.original_corner else 0
        roi = (x, y, x + rw, y + rh)
    x0, y0, x1, y1 = roi
    if not (0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h):
        raise ValueError('Erase region outside image')
    patch = a[y0:y1, x0:x1]
    bg = int(np.median(patch)) if a.ndim == 2 else tuple(np.median(patch, axis=(0, 1)).astype(int))
    if args.background is not None:
        bg = args.background if a.ndim == 2 else (args.background,) * 3
    draw = ImageDraw.Draw(im)
    draw.rectangle((x0, y0, x1-1, y1-1), fill=bg)
    removed_footer = None
    if footer and not getattr(args, 'keep_original_footer', False):
        _, fy, _, _ = footer
        footer_pixels = gray[fy:]
        # Crop only a separate, overwhelmingly black annotation strip.
        # Other erase boxes remain local fills inside the microscopy image.
        if gray[fy, 0] <= 8 and float(np.mean(footer_pixels <= 8)) >= .85:
            removed_footer = footer
            im = im.crop((0, 0, w, fy))
            h = fy
            draw = ImageDraw.Draw(im)
    footer_height = getattr(args, 'footer_height', 0)
    if footer_height and not removed_footer and x0 == 0 and x1 == w and y1 == h:
        # Extend the annotation footer instead of covering the microscopy area.
        new_h = max(h, y0 + footer_height)
        if new_h > h:
            expanded = Image.new(im.mode, (w, new_h), bg)
            expanded.paste(im, (0, 0))
            im, h = expanded, new_h
            draw = ImageDraw.Draw(im)
    clean_source = im.copy()
    choices = [n for n in (10, 20, 50, 100, 200, 500) if n/scale <= w-2*args.margin]
    matched = args.original_bar_nm if getattr(args, 'match_original_bar', False) else None
    if args.bar_nm is None and matched is None and not choices:
        raise ValueError('No automatic nm length fits this image; enter a smaller custom Length (nm)')
    length = args.bar_nm or matched or min(choices, key=lambda n: abs(n / scale - args.target_width))
    pixels = int(math.floor(length / scale + .5))
    if pixels < 1:
        raise ValueError('Bar rounds to less than one pixel')
    font = ImageFont.truetype(args.font, args.font_size) if args.font else ImageFont.load_default(size=args.font_size)
    label = f'{length:g} nm'
    tb = draw.textbbox((0, 0), label, font=font)
    tw, th = tb[2]-tb[0], tb[3]-tb[1]
    bw = max(pixels, tw)
    bh = th + args.gap + args.thickness
    if bw + 2*args.margin > w or bh + 2*args.margin > h:
        raise ValueError('Bar/label does not fit image')
    left = w-args.margin-bw if 'right' in args.corner else args.margin
    top = h-args.margin-bh if 'bottom' in args.corner else args.margin
    if getattr(args, 'bar_x', None) is not None:
        left = args.bar_x
    if getattr(args, 'bar_y', None) is not None:
        top = args.bar_y
        if removed_footer:
            top = min(top, h-bh)
    if not (0 <= left <= w-bw and 0 <= top <= h-bh):
        raise ValueError('Bar/label position outside image')
    by = top+th+args.gap if args.label_position == 'above' else top
    ty = top if args.label_position == 'above' else top+args.thickness+args.gap
    bx = left + (bw-pixels)//2
    color = 255 if args.color == 'white' else 0
    if a.ndim == 3:
        color = (color,)*3
    draw.rectangle((bx, by, bx+pixels-1, by+args.thickness-1), fill=color)
    draw.text((left+(bw-tw)/2-tb[0], ty-tb[1]), label, font=font, fill=color)
    out = args.output_dir / (path.stem + '_scalebar')
    if path.resolve() == out.with_suffix('.tif').resolve():
        raise ValueError('Output must differ from input')
    report = {'input': str(path), 'nm_per_pixel': scale, 'calibration_source': source,
            'measured_original_bar_pixels': measured_pixels,
            'original_bar_nm': args.original_bar_nm, 'recognized_scale_text': recognized_text,
            'label_reader': label_reader,
            'erase_box': roi, 'bar_nm': length, 'bar_pixels': pixels,
            'ideal_bar_pixels': length/scale, 'bar_box': [bx, by, bx+pixels, by+args.thickness],
            'annotation_box': [left, top, left+bw, top+bh], 'output_size': [w, h],
            'removed_black_footer': removed_footer,
            'pixel_rounding_error': abs(pixels-length/scale)}
    if getattr(args, 'inset_roi', None):
        from tem_inset import compose
        position = None if args.inset_x is None or args.inset_y is None else (args.inset_x, args.inset_y)
        im, report['inset'] = compose(im, clean_source, scale, args.inset_roi,
            args.inset_width, position, args.inset_color, args.inset_border,
            not args.inset_no_connector, args.inset_bar_nm,
            args.inset_connector_width, args.inset_connector_color)
    if render_only:
        return im, report
    result = np.asarray(im)
    tifffile.imwrite(str(out)+'.tif', result, metadata={'nm_per_pixel': scale}, photometric='minisblack' if a.ndim == 2 else 'rgb')
    im.save(str(out)+'.png')
    return report


def distribution(args):
    with args.csv.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if args.column not in (reader.fieldnames or []):
            raise ValueError(f'CSV missing {args.column!r}; columns: {reader.fieldnames}')
        values = []
        for rownum, row in enumerate(reader, 2):
            try:
                v = float(row[args.column])
                if not math.isfinite(v) or v <= 0:
                    raise ValueError()
                values.append(v)
            except (ValueError, TypeError):
                raise ValueError(f'Invalid diameter at CSV row {rownum}; all values must be positive and finite')
    if len(values) < 2:
        raise ValueError('At least two diameters required')
    data = np.asarray(values)
    mu, sigma = norm.fit(data)
    if sigma == 0:
        raise ValueError('Gaussian fit requires nonzero variation')
    edges = np.histogram_bin_edges(data, bins=args.bins)
    if args.bin_width:
        start = math.floor(data.min()/args.bin_width)*args.bin_width
        count = max(1, math.ceil((data.max()-start)/args.bin_width))
        edges = start + np.arange(count+1)*args.bin_width
    n = len(data)
    fig, ax = plt.subplots(figsize=(6.4, 4.8), constrained_layout=True)
    weights = np.full(n, 100/n) if args.y_mode == 'frequency' else None
    ax.hist(data, bins=edges, weights=weights, color='#8dbbd4', edgecolor='white', label='Measured diameters')
    x = np.linspace(min(edges[0], mu-3.5*sigma), max(edges[-1], mu+3.5*sigma), 700)
    multiplier = (100 if args.y_mode == 'frequency' else n)*np.diff(edges)[0]
    ax.plot(x, norm.pdf(x, mu, sigma)*multiplier, color='#b74439', lw=2, label='Gaussian fit (MLE)')
    ax.text(.97, .96, f'Mean ± std = {mu:.2f} ± {sigma:.2f} nm\nN = {n}', transform=ax.transAxes,
            ha='right', va='top', bbox={'facecolor': 'white', 'alpha': .9, 'edgecolor': 'none'})
    ax.set(xlabel='Diameter (nm)', ylabel='Frequency (%)' if args.y_mode == 'frequency' else 'Count')
    ax.set_ylim(bottom=0)
    ax.legend(loc='upper left', frameon=False)
    ax.spines[['top', 'right']].set_visible(False)
    stem = args.output_dir / 'size_distribution'
    fig.savefig(str(stem)+'.png', dpi=args.dpi)
    if args.pdf:
        fig.savefig(str(stem)+'.pdf')
    plt.close(fig)
    return {'column': args.column, 'N': n, 'mean_nm': mu, 'std_nm': sigma,
            'std_definition': 'population / Gaussian MLE, ddof=0', 'bin_edges': edges.tolist(), 'y_mode': args.y_mode}


def create_parser():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument('--tiff', type=Path, nargs='+', help='Single-frame uint8 TIFF files')
    p.add_argument('--csv', type=Path)
    p.add_argument('--column', default='diameter_nm', help='Diameter column, values in nm')
    p.add_argument('--output-dir', type=Path, default=Path('outputs'))
    p.add_argument('--nm-per-pixel', type=positive)
    p.add_argument('--original-bar-nm', type=positive)
    p.add_argument('--original-bar-px', type=positive, help='Measured original bar width in pixels')
    p.add_argument('--ocr-default-unit', choices=['nm', 'um'], default='nm', help='Unit used for an unambiguous OCR number when unit text is unreadable')
    p.add_argument('--measure-original-bar', action='store_true', help='Measure original bar per image and read its nm/um text with OS OCR when --original-bar-nm is omitted')
    p.add_argument('--measure-box', type=rectangle, help='Original bar-only search rectangle; otherwise detect separate footer')
    p.add_argument('--image-config', type=Path, help='JSON mapping image filename to per-image option overrides (underscore keys)')
    p.add_argument('--bar-nm', type=positive, help='Explicit new length; otherwise select 10/20/50/100/200/500 nm')
    p.add_argument('--match-original-bar', action='store_true', help='Default the new nm length to the detected or supplied original label')
    p.add_argument('--target-width', type=positive, default=250)
    corners = ['bottom-right', 'bottom-left', 'top-right', 'top-left']
    p.add_argument('--corner', choices=corners, default='bottom-right')
    p.add_argument('--original-corner', choices=corners, default='bottom-right')
    p.add_argument('--erase-box', type=rectangle, help='Explicit original annotation rectangle; overrides footer detection')
    p.add_argument('--erase-width', type=int, default=420)
    p.add_argument('--erase-height', type=int, default=130)
    p.add_argument('--background', type=int, choices=range(256), metavar='0..255', help='Default: median of erased region')
    p.add_argument('--color', choices=['black', 'white'], default='white')
    p.add_argument('--thickness', type=int, default=7)
    p.add_argument('--font-size', type=int, default=26)
    p.add_argument('--font', help='Optional TrueType font file')
    p.add_argument('--margin', type=int, default=9)
    p.add_argument('--gap', type=int, default=5)
    p.add_argument('--bar-x', type=int, help='Custom annotation left coordinate, in full-resolution pixels')
    p.add_argument('--bar-y', type=int, help='Custom annotation top coordinate, in full-resolution pixels')
    p.add_argument('--footer-height', type=int, default=0, help='Minimum height of a full-width annotation footer; extends canvas without covering microscopy')
    p.add_argument('--keep-original-footer', action='store_true', help='Keep the original black annotation footer instead of cropping it off')
    p.add_argument('--label-position', choices=['above', 'below'], default='above')
    p.add_argument('--inset-roi', type=rectangle, help='Inset source rectangle x0,y0,x1,y1, in cleaned image pixels')
    p.add_argument('--inset-width', type=int, default=500)
    p.add_argument('--inset-x', type=int)
    p.add_argument('--inset-y', type=int)
    p.add_argument('--inset-color', choices=['white', 'black'], default='white')
    p.add_argument('--inset-border', type=int, default=4)
    p.add_argument('--inset-no-connector', action='store_true')
    p.add_argument('--inset-connector-width', type=int, default=4)
    p.add_argument('--inset-connector-color', choices=['white', 'black'], default='white')
    p.add_argument('--inset-bar-nm', type=positive, help='Inset bar length; default selects a readable length automatically')
    bins = p.add_mutually_exclusive_group()
    bins.add_argument('--bins', type=int, default=12)
    bins.add_argument('--bin-width', type=positive)
    p.add_argument('--y-mode', choices=['count', 'frequency'], default='count')
    p.add_argument('--dpi', type=int, default=300)
    p.add_argument('--pdf', action='store_true')
    return p


def main():
    p = create_parser()
    args = p.parse_args()
    if not args.tiff and not args.csv:
        p.error('Provide --tiff and/or --csv')
    if any(getattr(args, k) <= 0 for k in ('thickness', 'font_size', 'erase_width', 'erase_height', 'bins')) or args.margin < 0 or args.gap < 0 or args.dpi < 300:
        p.error('Sizes/bins must be positive; margin/gap >= 0; dpi >= 300')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    try:
        config = json.loads(args.image_config.read_text(encoding='utf-8-sig')) if args.image_config else {}
        images = []
        for path in args.tiff or []:
            local = copy.copy(args)
            for key, value in config.get(path.name, {}).items():
                if key not in {'nm_per_pixel', 'original_bar_nm', 'original_bar_px', 'measure_original_bar', 'measure_box', 'erase_box', 'bar_nm', 'match_original_bar', 'ocr_default_unit', 'keep_original_footer', 'corner', 'original_corner', 'color', 'background', 'font_size', 'thickness', 'margin', 'gap', 'label_position', 'target_width'}:
                    raise ValueError(f'Unsupported per-image option: {key}')
                setattr(local, key, value)
            images.append(redraw(path, local))
        report = {'images': images}
        if args.csv:
            report['distribution'] = distribution(args)
        report_path = args.output_dir / 'run_report.json'
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
        print(json.dumps(report, indent=2, ensure_ascii=False))
    except (ValueError, OSError) as e:
        p.exit(2, f'Error: {e}\n')


if __name__ == '__main__':
    main()
