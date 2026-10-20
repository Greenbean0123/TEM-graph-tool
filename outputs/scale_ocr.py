"""Read scale-label text using the OS OCR engine; no cloud or model download."""
import ctypes as C
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image, ImageOps


def parse_scale_text(lines):
    values = {}
    for item in lines:
        text = item['text']
        confidence = item.get('confidence')
        if confidence is not None and confidence < .8:
            continue
        for match in re.finditer(r'(?<![\w.])(\d+(?:[.,]\d+)?)\s*(nm|[uµμ]m)(?!\w)', text, re.I):
            number = float(match[1].replace(',', '.'))
            nm = number * (1 if match[2].lower() == 'nm' else 1000)
            if math.isfinite(nm) and nm > 0:
                values[nm] = match[0]
    if len(values) != 1:
        raise ValueError('Could not read one unambiguous nm/µm scale label. Enter Original label (nm) or select a tighter original annotation box.')
    nm, text = next(iter(values.items()))
    return nm, text


def mac_text(path):
    """Vision Objective-C bridge using stdlib ctypes on both arm64 and x86_64."""
    C.CDLL('/System/Library/Frameworks/Foundation.framework/Foundation')
    C.CDLL('/System/Library/Frameworks/Vision.framework/Vision')
    objc = C.CDLL('/usr/lib/libobjc.A.dylib')
    objc.objc_getClass.argtypes = [C.c_char_p]
    objc.objc_getClass.restype = C.c_void_p
    objc.sel_registerName.argtypes = [C.c_char_p]
    objc.sel_registerName.restype = C.c_void_p

    def cls(name):
        value = objc.objc_getClass(name.encode())
        if not value:
            raise RuntimeError('macOS Vision text recognition is unavailable')
        return value

    def send(receiver, name, *args, result=C.c_void_p, types=()):
        function = C.CFUNCTYPE(result, C.c_void_p, C.c_void_p, *types)(('objc_msgSend', objc))
        return function(receiver, objc.sel_registerName(name.encode()), *args)

    def string(value):
        return send(cls('NSString'), 'stringWithUTF8String:', value.encode('utf-8'), types=(C.c_char_p,))

    pool = send(send(cls('NSAutoreleasePool'), 'alloc'), 'init')
    request = handler = None
    try:
        request = send(send(cls('VNRecognizeTextRequest'), 'alloc'), 'init')
        send(request, 'setRecognitionLevel:', 0, result=None, types=(C.c_long,))
        send(request, 'setUsesLanguageCorrection:', False, result=None, types=(C.c_bool,))
        languages = send(cls('NSArray'), 'arrayWithObject:', string('en-US'), types=(C.c_void_p,))
        send(request, 'setRecognitionLanguages:', languages, result=None, types=(C.c_void_p,))
        url = send(cls('NSURL'), 'fileURLWithPath:', string(str(Path(path).resolve())), types=(C.c_void_p,))
        options = send(cls('NSDictionary'), 'dictionary')
        handler = send(send(cls('VNImageRequestHandler'), 'alloc'), 'initWithURL:options:', url, options, types=(C.c_void_p, C.c_void_p))
        requests = send(cls('NSArray'), 'arrayWithObject:', request, types=(C.c_void_p,))
        error = C.c_void_p()
        okay = send(handler, 'performRequests:error:', requests, C.byref(error), result=C.c_bool, types=(C.c_void_p, C.POINTER(C.c_void_p)))
        if not okay:
            raise RuntimeError('macOS Vision could not read the original annotation')
        observations = send(request, 'results')
        lines = []
        for index in range(send(observations, 'count', result=C.c_ulong)):
            observation = send(observations, 'objectAtIndex:', index, types=(C.c_ulong,))
            candidates = send(observation, 'topCandidates:', 1, types=(C.c_ulong,))
            if not send(candidates, 'count', result=C.c_ulong):
                continue
            candidate = send(candidates, 'firstObject')
            raw = send(send(candidate, 'string'), 'UTF8String', result=C.c_char_p)
            confidence = send(candidate, 'confidence', result=C.c_float)
            lines.append({'text': raw.decode('utf-8'), 'confidence': confidence})
        return lines
    finally:
        if handler:
            send(handler, 'release', result=None)
        if request:
            send(request, 'release', result=None)
        send(pool, 'drain', result=None)


def windows_text(path):
    script = r'''
[Console]::OutputEncoding = [Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]
$asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
  $_.Name -eq 'AsTask' -and $_.IsGenericMethodDefinition -and $_.GetGenericArguments().Count -eq 1 -and
  $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
} | Select-Object -First 1
function Await($operation, $type) {
  $task = $asTask.MakeGenericMethod($type).Invoke($null, @($operation))
  $task.Wait()
  $task.Result
}
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($env:TEM_OCR_IMAGE)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$null = [Windows.Globalization.Language, Windows.Globalization, ContentType=WindowsRuntime]
$language = New-Object Windows.Globalization.Language 'en-US'
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($language)
if ($null -eq $engine) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages() }
if ($null -eq $engine) { throw 'Windows OCR language is unavailable' }
$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
@{text=$result.Text} | ConvertTo-Json -Compress
$bitmap.Dispose()
$stream.Dispose()
'''
    import os
    env = dict(os.environ, TEM_OCR_IMAGE=str(Path(path).resolve()))
    process = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                             capture_output=True, text=True, encoding='utf-8-sig', env=env, timeout=30,
                             creationflags=subprocess.CREATE_NO_WINDOW)
    if process.returncode:
        raise RuntimeError('Windows text recognition failed; enter the original nm label manually')
    return [json.loads(process.stdout)]


def read_scale_label(array, region):
    x0, y0, x1, y1 = region
    patch = Image.fromarray(array[y0:y1, x0:x1]).convert('L')
    values = np.asarray(patch)
    bg = float(np.median(values))
    yy, xx = np.where(np.abs(values.astype(float)-bg) > 80)
    if len(xx):
        patch = patch.crop((max(0, int(xx.min())-5), max(0, int(yy.min())-5),
                            min(patch.width, int(xx.max())+6), min(patch.height, int(yy.max())+6)))
    if bg < 128:
        patch = ImageOps.invert(patch)
    factor = min(3, 4000/max(patch.width, 1))
    if factor > 1:
        patch = patch.resize((round(patch.width*factor), round(patch.height*factor)), Image.Resampling.LANCZOS)
    patch = ImageOps.expand(patch, border=24, fill=255)
    with tempfile.TemporaryDirectory(prefix='tem_scale_ocr_') as folder:
        path = Path(folder)/'original_label.png'
        patch.save(path)
        if sys.platform == 'darwin':
            lines = mac_text(path)
            engine = 'macOS Vision'
        elif sys.platform == 'win32':
            lines = windows_text(path)
            engine = 'Windows OCR'
        else:
            raise ValueError('Automatic label reading requires macOS or Windows; enter Original label (nm) manually')
    nm, text = parse_scale_text(lines)
    return nm, text, engine
