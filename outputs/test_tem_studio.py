"""Meaningful rendering/calibration and desktop-state regression checks."""
import copy
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

import numpy as np
import tifffile

import tem_scalebar_distribution as core
from tem_studio import TEMStudio


class TEMTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def image(self, name, width):
        a = np.full((512, 512), 145, dtype=np.uint8)
        a[450:] = 0
        a[480:486, 100:100+width] = 255
        path = self.folder/name
        tifffile.imwrite(path, a)
        return path, a

    def test_each_image_measures_its_own_bar_and_preserves_other_pixels(self):
        args = core.create_parser().parse_args([])
        args.measure_original_bar = True
        args.original_bar_nm = 100
        args.bar_nm = 50
        args.bar_x, args.bar_y = 230, 300
        args.output_dir = self.folder
        for width in (101, 151):
            path, original = self.image(f'{width}.tif', width)
            before = path.read_bytes()
            im, r = core.redraw(path, copy.copy(args), render_only=True)
            self.assertEqual(r['measured_original_bar_pixels'], width)
            self.assertAlmostEqual(r['nm_per_pixel'], 100/width)
            self.assertLessEqual(r['pixel_rounding_error'], .5)
            mask = np.ones(original.shape, dtype=bool)
            mask[450:] = False
            x0, y0, x1, y1 = r['annotation_box']
            mask[y0:y1, x0:x1] = False
            self.assertTrue(np.array_equal(np.asarray(im)[mask], original[mask]))
            self.assertEqual(im.size, (512, 512))
            self.assertFalse(np.asarray(im)[450:].any())
            self.assertEqual(path.read_bytes(), before)

    def test_gui_retains_per_image_settings_and_drag_position(self):
        one, _ = self.image('one.tif', 101)
        two, _ = self.image('two.tif', 151)
        app = TEMStudio(enable_updates=False)
        app.withdraw()
        try:
            app.load_files([str(one)])
            app.vars['original_bar_nm'].set('100')
            app.vars['bar_nm'].set('50')
            app.vars['font_size'].set('30')
            app.refresh_tem(quiet=True)
            self.assertEqual(app.report['measured_original_bar_pixels'], 101)
            app.load_files([str(two)])
            self.assertEqual(app.vars['original_bar_nm'].get(), '')
            app.vars['original_bar_nm'].set('200')
            app.vars['bar_nm'].set('100')
            app.refresh_tem(quiet=True)
            self.assertEqual(app.report['measured_original_bar_pixels'], 151)
            app.listbox.selection_clear(0, 'end')
            app.listbox.selection_set(0)
            app.select_file()
            self.assertEqual(app.vars['original_bar_nm'].get(), '100')
            self.assertEqual(app.vars['font_size'].get(), '30')
            app.canvas.config(width=700, height=700)
            app.deiconify()
            app.update()
            app.refresh_tem(quiet=True)
            scale, ox, oy = app.transform
            box = app.report['annotation_box']
            x, y = (box[0]+box[2])/2, (box[1]+box[3])/2
            app.press(SimpleNamespace(x=ox+x*scale, y=oy+y*scale))
            app.release(SimpleNamespace(x=ox+(x-30)*scale, y=oy+(y-40)*scale))
            self.assertAlmostEqual(int(app.vars['bar_x'].get()), box[0]-30, delta=1)
            self.assertAlmostEqual(int(app.vars['bar_y'].get()), box[1]-40, delta=1)
            app.vars['color'].set('black')
            app.refresh_tem(quiet=True)
            x0, y0, x1, y1 = app.report['bar_box']
            self.assertTrue((np.asarray(app.preview_image)[y0:y1, x0:x1] == 0).all())
        finally:
            app.close()


if __name__ == '__main__':
    unittest.main()
