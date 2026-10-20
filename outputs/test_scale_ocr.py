"""Scale-label recognition, unit conversion and import-field regression tests."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import tifffile

import scale_ocr
import tem_scalebar_distribution as core
from tem_studio import TEMStudio


def scale_fixture(folder, value=50, width=151, name='scale.tif'):
    a = np.full((800, 1024), 145, dtype=np.uint8)
    a[700:] = 0
    a[745:753, 420:420+width] = 255
    im = Image.fromarray(a)
    ImageDraw.Draw(im).text((420+width+24, 714), f'{value:g} nm', font=ImageFont.load_default(size=44), fill=255)
    path = Path(folder)/name
    tifffile.imwrite(path, np.asarray(im))
    return path


class ScaleOCRTests(unittest.TestCase):
    def test_units_and_ambiguity(self):
        for text, expected in [('50 nm', 50), ('200nm', 200), ('0.5 µm', 500), ('1 um', 1000)]:
            self.assertEqual(scale_ocr.parse_scale_text([{'text': text, 'confidence': .99}])[0], expected)
        for lines in [[{'text': '50 nm', 'confidence': .2}], [{'text': '50'}], [{'text': '50 nm / 200 nm'}], [{'text': '500 m'}]]:
            with self.assertRaises(ValueError):
                scale_ocr.parse_scale_text(lines)

    def test_independent_auto_label_and_bar_width(self):
        with tempfile.TemporaryDirectory() as folder:
            args = core.create_parser().parse_args([])
            args.measure_original_bar = True
            for nm, width in [(50, 151), (200, 251)]:
                path = scale_fixture(folder, nm, width)
                with patch.object(scale_ocr, 'read_scale_label', return_value=(nm, f'{nm} nm', 'test reader')):
                    im, report = core.redraw(path, copy.copy(args), render_only=True)
                self.assertEqual(report['original_bar_nm'], nm)
                self.assertEqual(report['measured_original_bar_pixels'], width)
                self.assertAlmostEqual(report['nm_per_pixel'], nm/width)
                self.assertEqual(im.size, (1024, 800))

    def test_gui_import_populates_original_calibration(self):
        with tempfile.TemporaryDirectory() as folder:
            path = scale_fixture(folder)
            app = TEMStudio(enable_updates=False)
            app.withdraw()
            try:
                with patch.object(scale_ocr, 'read_scale_label', return_value=(50, '50 nm', 'test reader')):
                    app.load_files([str(path)])
                self.assertIsNotNone(app.report, app.status.get())
                self.assertEqual(app.vars['original_bar_nm'].get(), '50')
                self.assertEqual(app.vars['original_bar_px'].get(), '151')
                self.assertEqual(app.vars['bar_nm'].get(), '50')
                self.assertEqual(app.report['bar_pixels'], 151)
                self.assertAlmostEqual(float(app.vars['nm_per_pixel'].get()), 50/151)
            finally:
                app.close()

    @unittest.skipUnless(sys.platform == 'darwin', 'Requires the actual macOS Vision framework')
    def test_native_mac_reader_without_manual_nm(self):
        with tempfile.TemporaryDirectory() as folder:
            for nm in (50, 200):
                path = scale_fixture(folder, nm)
                args = core.create_parser().parse_args([])
                args.measure_original_bar = True
                _, report = core.redraw(path, args, render_only=True)
                self.assertEqual(report['original_bar_nm'], nm)
                self.assertEqual(report['measured_original_bar_pixels'], 151)


if __name__ == '__main__':
    unittest.main()
