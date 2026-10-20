"""Meaningful rendering/calibration and desktop-state regression checks."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import numpy as np
import tifffile

import tem_scalebar_distribution as core
from tem_studio import TEMStudio


class TEMTests(unittest.TestCase):
    def test_independent_exports_custom_default_names_cancel_and_source_protection(self):
        path, _ = self.image('source.v1.tif', 101)
        original = path.read_bytes()
        app = TEMStudio(enable_updates=False)
        app.withdraw()
        try:
            app.load_files([str(path)])
            app.vars['original_bar_nm'].set('100')
            app.vars['font_size'].set('30')
            app.vars['bar_nm'].set('50')
            app.refresh_tem(quiet=True)
            csv_path = self.folder/'values.csv'
            csv_path.write_text('diameter_nm\n10\n20\n30\n')
            app.set_csv(csv_path)
            app.pdf.set(True)
            def export(method, view, folder, name, formats=None, report=True, files=None):
                folder.mkdir()
                app.view = view
                options = None if name is None else dict(directory=folder, name=name, formats=formats or (['png', 'pdf'] if method == app.export_distribution else ['png', 'tif']), report=report, files=files)
                with patch.object(app, 'choose_export', return_value=options), patch('tem_studio.messagebox.showinfo'), patch('tem_studio.messagebox.showerror', side_effect=AssertionError):
                    method()
            tem = self.folder/'tem'
            export(app.export_tem, 'distribution', tem, 'TEM figure.v1.png')
            self.assertEqual({p.suffix for p in tem.iterdir()}, {'.png', '.tif', '.json'})
            self.assertTrue((tem/'TEM figure.v1.tif').exists())
            dist = self.folder/'dist'
            export(app.export_distribution, 'tem', dist, 'Distribution.v1.pdf')
            self.assertEqual({p.suffix for p in dist.iterdir()}, {'.png', '.pdf', '.json'})
            self.assertTrue((dist/'Distribution.v1.pdf').exists())
            defaults = self.folder/'defaults'
            export(app.export_tem, 'distribution', defaults, '   ')
            self.assertTrue((defaults/'source.v1_scalebar.tif').exists())
            distribution_defaults = self.folder/'distribution_defaults'
            export(app.export_distribution, 'tem', distribution_defaults, '')
            self.assertTrue((distribution_defaults/'size_distribution.png').exists())
            cancelled = self.folder/'cancelled'
            export(app.export_tem, 'tem', cancelled, None)
            self.assertFalse(list(cancelled.iterdir()))
            png_only = self.folder/'png_only'
            export(app.export_tem, 'distribution', png_only, 'just TEM', ['png'], False)
            self.assertEqual({p.name for p in png_only.iterdir()}, {'just TEM.png'})
            tif_only = self.folder/'tif_only'
            export(app.export_tem, 'distribution', tif_only, 'just TEM', ['tif'], False)
            self.assertEqual({p.name for p in tif_only.iterdir()}, {'just TEM.tif'})
            dist_png = self.folder/'dist_png'
            export(app.export_distribution, 'tem', dist_png, 'just size', ['png'], False)
            self.assertEqual({p.name for p in dist_png.iterdir()}, {'just size.png'})
            args = app.get_args(out=self.folder)
            args.tem_name = path.stem
            with self.assertRaisesRegex(ValueError, 'differ from input'):
                core.redraw(path, args)
            other, _ = self.image('other.tif', 151)
            args.tem_name = other.stem
            args.protected_inputs = [path, other]
            with self.assertRaisesRegex(ValueError, 'differ from input'):
                core.redraw(path, args)
            app.load_files([str(other)])
            app.vars['original_bar_nm'].set('200')
            app.vars['font_size'].set('30')
            app.vars['bar_nm'].set('50')
            app.refresh_tem(quiet=True)
            batch = self.folder/'batch'
            export(app.export_all, 'distribution', batch, 'batch figure.v1.png', ['png'], False, [path, other])
            self.assertEqual({p.name for p in batch.iterdir()}, {'batch figure.v1_001.png', 'batch figure.v1_002.png'})
            subset = self.folder/'subset'
            export(app.export_all, 'tem', subset, '', ['png'], False, [other])
            self.assertEqual({p.name for p in subset.iterdir()}, {'other_scalebar.png'})
            unvisited = self.folder/'unvisited.tif'
            visited = self.folder/'visited.tif'
            for destination in (unvisited, visited):
                tifffile.imwrite(destination, np.full((512, 512), 145, dtype=np.uint8), metadata={'nm_per_pixel': 1})
            app.load_files([str(unvisited), str(visited)])
            fresh_batch = self.folder/'fresh_batch'
            export(app.export_all, 'tem', fresh_batch, '', ['png'], False, [unvisited])
            self.assertTrue((fresh_batch/'unvisited_scalebar.png').exists())
            self.assertEqual(len(app.session_data()['images']), 4)
            self.assertEqual(path.read_bytes(), original)
            for invalid in ('../escape', 'bad/name', 'NUL', 'figure?.png'):
                with self.assertRaises(ValueError):
                    core.export_stem(self.folder, invalid, 'default', {'.png'})
        finally:
            app.close()

    def test_inset_samples_clean_pixels_and_recalibrates(self):
        from PIL import Image
        from tem_inset import compose
        source = Image.fromarray(np.tile(np.arange(256, dtype=np.uint8), (512, 2)))
        annotated = Image.new('L', source.size, 0)
        for width in (160, 240):
            out, r = compose(annotated, source, .5, (20, 20, 100, 100),
                             width, (250, 20), bar_nm=10)
            self.assertEqual(r['magnification'], width/80)
            self.assertEqual(r['bar_pixels'], round(10/(.5/(width/80))))
            self.assertLessEqual(r['pixel_rounding_error'], .5)
            expected = source.crop((20, 20, 100, 100)).resize((width, width), Image.Resampling.LANCZOS)
            self.assertEqual(out.getpixel((270, 40)), expected.getpixel((20, 20)))
            self.assertEqual(out.getpixel((0, 511)), 0)

    def test_two_connectors_have_independent_color_and_width(self):
        from PIL import Image
        from tem_inset import compose
        source = Image.new('L', (512, 512), 145)
        out, _ = compose(source, source, .5, (20, 20, 100, 100), 160,
                         (250, 20), color='white', connector_width=6, connector_color='black')
        self.assertEqual(out.getpixel((180, 20)), 0)
        self.assertEqual(out.getpixel((180, 22)), 0)
        self.assertEqual(out.getpixel((180, 141)), 0)
        self.assertEqual(out.getpixel((180, 65)), 145)

    def test_hidden_inset_bar_leaves_source_pixels_visible(self):
        from PIL import Image
        from tem_inset import compose
        source = Image.new('L', (512, 512), 145)
        shown, _ = compose(source, source, .5, (20, 20, 100, 100), 160, (250, 20))
        hidden, r = compose(source, source, .5, (20, 20, 100, 100), 160, (250, 20),
                            bar_nm=100000, show_scalebar=False)
        self.assertFalse(r['show_scalebar'])
        self.assertIsNone(r['bar_pixels'])
        np.testing.assert_array_equal(np.asarray(hidden)[25:175, 255:405], 145)
        self.assertFalse(np.array_equal(np.asarray(shown), np.asarray(hidden)))

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
            mask = np.ones((450, 512), dtype=bool)
            x0, y0, x1, y1 = r['annotation_box']
            mask[y0:y1, x0:x1] = False
            self.assertTrue(np.array_equal(np.asarray(im)[mask], original[:450][mask]))
            self.assertEqual(im.size, (512, 450))
            self.assertEqual(r['removed_black_footer'], (0, 450, 512, 512))
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
            app.tool('inset')
            scale, ox, oy = app.transform
            app.press(SimpleNamespace(x=ox+30*scale, y=oy+30*scale))
            app.release(SimpleNamespace(x=ox+130*scale, y=oy+130*scale))
            self.assertIn('inset', app.report)
            box = app.report['inset']['box']
            app.press(SimpleNamespace(x=ox+(box[0]+30)*scale, y=oy+(box[1]+30)*scale))
            app.release(SimpleNamespace(x=ox+(box[0]+10)*scale, y=oy+(box[1]+50)*scale))
            self.assertEqual(app.mode.get(), 'move')
            self.assertLessEqual(app.report['inset']['pixel_rounding_error'], .5)
            args = app.get_args(out=self.folder)
            r = core.redraw(one, args)
            self.assertIn('inset', r)
            self.assertTrue((self.folder/'one_scalebar.png').exists())
            main_bar = list(app.report['bar_box'])
            x0, y0, x1, y1 = main_bar
            main_pixels = np.asarray(app.preview_image)[y0:y1, x0:x1].copy()
            app.vars['inset_show_scalebar'].set('No')
            app.refresh_tem(quiet=True)
            self.assertFalse(app.report['inset']['show_scalebar'])
            self.assertTrue(app.get_args().inset_no_scalebar)
            self.assertEqual(main_bar, app.report['bar_box'])
            np.testing.assert_array_equal(np.asarray(app.preview_image)[y0:y1, x0:x1], main_pixels)
        finally:
            app.close()


if __name__ == '__main__':
    import sys
    if sys.platform == 'darwin' and len(sys.argv) == 1:
        # Cocoa/Tk requires one root lifecycle per process; isolate GUI cases.
        import subprocess
        for name in unittest.defaultTestLoader.getTestCaseNames(TEMTests):
            subprocess.run([sys.executable, __file__, 'TEMTests.'+name], check=True)
    else:
        unittest.main()
