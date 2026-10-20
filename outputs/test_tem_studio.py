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
    def test_vector_distribution_overlay_and_deferred_pane_resize(self):
        import xml.etree.ElementTree as ET
        from PIL import Image
        csv = self.folder/'diameters.csv'
        csv.write_text('diameter_nm\n20\n30\n40\n50\n60\n')
        source = self.folder/'vector source.tif'
        tifffile.imwrite(source, np.full((1024, 1024), 145, dtype=np.uint8), metadata={'nm_per_pixel': 1})
        before = source.read_bytes()
        args = core.create_parser().parse_args(['--csv', str(csv), '--nm-per-pixel', '1', '--overlay-distribution',
            '--overlay-width', '400', '--overlay-x', '30', '--overlay-y', '40', '--bar-nm', '100',
            '--output-dir', str(self.folder), '--tem-formats', 'png', 'tif', 'pdf', 'svg'])
        stages = []
        args.progress = lambda value, text: stages.append((value, text))
        args.overlay_label_size, args.overlay_tick_size, args.overlay_stats_size = 13, 8, 11
        image, report = core.redraw(source, args, render_only=True)
        self.assertEqual([value for value, _ in stages], [5, 15, 30, 40, 75, 90])
        from distribution_overlay import panel_figure
        fig, _ = panel_figure(args, 400)
        try:
            ax = fig.axes[0]
            self.assertEqual(ax.xaxis.label.get_fontsize(), 13)
            self.assertEqual(ax.get_xticklabels()[0].get_fontsize(), 8)
            self.assertEqual(ax.texts[0].get_fontsize(), 11)
        finally:
            core.plt.close(fig)
        panel = report['distribution_overlay']
        self.assertEqual(panel['box'], [30, 40, 430, 340])
        self.assertEqual(panel['N'], 5)
        self.assertEqual(panel['mean_nm'], 40)
        self.assertAlmostEqual(panel['std_nm'], np.std([20, 30, 40, 50, 60]))
        self.assertTrue((np.asarray(image)[400:500, 0:200] == 145).all())
        core.redraw(source, args)
        stem = self.folder/'vector source_scalebar'
        with Image.open(str(stem)+'.png') as png:
            self.assertTrue(np.array_equal(np.asarray(png), np.asarray(image)))
        self.assertEqual(tifffile.imread(str(stem)+'.tif').shape, (1024, 1024, 3))
        svg = ET.parse(str(stem)+'.svg')
        ns = {'s': 'http://www.w3.org/2000/svg'}
        self.assertEqual(len(svg.findall('.//s:image', ns)), 1)  # TEM only; chart stays vector.
        self.assertGreater(len(svg.findall('.//s:path', ns)), 20)
        self.assertTrue(Path(str(stem)+'.pdf').read_bytes().startswith(b'%PDF'))
        args.distribution_formats = ['svg']
        core.distribution(args)
        standalone = ET.parse(self.folder/'size_distribution.svg')
        self.assertEqual(len(standalone.findall('.//s:image', ns)), 0)
        self.assertEqual(source.read_bytes(), before)
        args.overlay_bar_color = '#00aa44'
        args.overlay_curve_color = '#9900cc'
        args.overlay_bar_alpha = .25
        args.overlay_curve_alpha = .4
        args.overlay_background_alpha = .5
        core.redraw(source, args)
        vector_text = Path(str(stem)+'.svg').read_text(encoding='utf-8')
        self.assertIn('#00aa44', vector_text)
        self.assertIn('#9900cc', vector_text)
        self.assertIn('opacity: 0.25', vector_text)
        args.overlay_bar_alpha = args.overlay_curve_alpha = args.overlay_background_alpha = 0
        transparent, _ = core.redraw(source, args, render_only=True)
        self.assertTrue((np.asarray(transparent)[190, 230] == 145).all())
        args.y_mode = 'density'
        fig, _ = core.distribution_figure(args)
        try:
            bars = fig.axes[0].patches
            self.assertAlmostEqual(sum(bar.get_height()*bar.get_width() for bar in bars), 1)
        finally:
            core.plt.close(fig)
        app = TEMStudio(enable_updates=False)
        try:
            app.geometry('1200x800')
            app.update()
            app.load_files([str(source)])
            app.set_csv(csv)
            app.loading = True
            for key, value in dict(overlay_enabled='Yes', overlay_width='400', overlay_x='30', overlay_y='40').items():
                app.vars[key].set(value)
            app.loading = False
            app.refresh_tem(quiet=True)
            self.assertIn(csv.name, app.file_hint.get())
            self.assertEqual(app.overlay_progress.get(), 100)
            self.assertIn('preview ready', app.overlay_progress_text.get())
            scale, ox, oy = app.transform
            app.press(SimpleNamespace(x=ox+130*scale, y=oy+140*scale))
            app.release(SimpleNamespace(x=ox+180*scale, y=oy+160*scale))
            self.assertEqual(app.report['distribution_overlay']['box'][:2], [80, 60])
            # Moving a sash schedules no heavy preview renders until release.
            initial = app.panes.sashpos(0)
            with patch.object(app.panes, 'identify', return_value=0):
                self.assertEqual(app.begin_pane_resize(app.panes, SimpleNamespace(x=initial, y=10)), 'break')
            with patch.object(app, 'draw_preview') as draw:
                for delta in range(20):
                    self.assertEqual(app.preview_pane_resize(SimpleNamespace(x=initial+delta, y=10)), 'break')
                    app.schedule_preview()
                    app.update()
                draw.assert_not_called()
                self.assertEqual(app.panes.sashpos(0), initial)
                self.assertIsNone(app.render_pending)
                app.end_pane_resize()
                app.update_idletasks()
                draw.assert_called_once_with(quick=True)
                self.assertEqual(app.panes.sashpos(0), initial+19)
                self.assertIsNotNone(app.render_pending)
            app.draw_preview(quick=True)
            self.assertIsNone(app.render_key)
            app.draw_preview()
            self.assertIsNotNone(app.render_key)
            self.assertEqual(source.read_bytes(), before)
        finally:
            app.close()

    def test_appearance_zoom_cache_and_source_names_do_not_change_scientific_output(self):
        path, _ = self.image('current image.tif', 101)
        original = path.read_bytes()
        app = TEMStudio(enable_updates=False)
        try:
            app.geometry('1100x700')
            app.update()
            app.load_files([str(path)])
            app.loading = True
            for key, value in dict(original_bar_nm='100', bar_nm='50', font_size='30').items():
                app.vars[key].set(value)
            app.loading = False
            app.refresh_tem(quiet=True)
            baseline = np.asarray(app.preview_image).copy()
            settings = app.image_state()
            self.assertIn(path.name, app.file_hint.get())
            item, photo = app.image_item, app.photo
            app.draw_preview()
            self.assertIs(app.photo, photo)
            for tab in app.scroll_tabs:
                tab.master.select(tab)
                app.update()
            self.assertEqual(app.image_item, item)
            app.appearance.theme.set('Dark')
            app.appearance.scale.set('125%')
            app.appearance.apply()
            app.update()
            self.assertEqual(app.listbox.cget('background'), app.appearance.colors['input'])
            self.assertEqual(app.scroll_tabs[0].canvas.cget('background'), app.appearance.colors['bg'])
            font = app.appearance.style.lookup('TLabel', 'font')
            self.assertTrue(font)
            app.zoom_preview(2)
            app.pan_start(SimpleNamespace(x=100, y=100))
            app.pan_motion(SimpleNamespace(x=125, y=115))
            scale, ox, oy = app.transform
            self.assertEqual(app.point(SimpleNamespace(x=ox+200*scale, y=oy+150*scale)), (200, 150))
            self.assertEqual(app.image_state(), settings)
            self.assertTrue(np.array_equal(np.asarray(app.preview_image), baseline))
            # Drag remains in original image coordinates while zoomed and panned.
            box = app.report['annotation_box']
            x, y = (box[0]+box[2])/2, (box[1]+box[3])/2
            app.press(SimpleNamespace(x=ox+x*scale, y=oy+y*scale))
            app.release(SimpleNamespace(x=ox+(x-15)*scale, y=oy+(y-10)*scale))
            self.assertAlmostEqual(int(app.vars['bar_x'].get()), box[0]-15, delta=1)
            self.assertAlmostEqual(int(app.vars['bar_y'].get()), box[1]-10, delta=1)
            app.fit_preview()
            self.assertIsNone(app.preview_zoom)
            csv = self.folder/'this distribution.csv'
            csv.write_text('diameter_nm\n20\n30\n40\n')
            app.set_csv(csv)
            app.refresh_distribution(quiet=True)
            self.assertEqual(app.file_hint.get(), 'Distribution CSV: '+csv.name)
            app.show_original()
            self.assertEqual(app.file_hint.get(), 'Current TIFF: '+path.name)
            self.assertEqual(path.read_bytes(), original)
        finally:
            app.close()

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
                tifffile.imwrite(destination, np.full((1024, 1024), 145, dtype=np.uint8), metadata={'nm_per_pixel': 1})
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
        args.font_size, args.thickness = 26, 7  # Small synthetic fixture.
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
            app.vars['font_size'].set('30')
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
