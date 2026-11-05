# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: package the S7CommPlus gateway CLI as one file.

Build (Windows, produces ``dist/s7gateway.exe``)::

    pyinstaller --clean --noconfirm gateway/s7gateway.spec

Build (Linux, produces ``dist/s7gateway`` -- a Linux binary, not an
``.exe``; PyInstaller cannot cross-compile to Windows)::

    pyinstaller --clean --noconfirm gateway/s7gateway.spec

Why ``collect_all('s7commplus')``: the gateway imports
``s7commplus.client`` lazily inside ``connect()``, and the library
itself loads submodules (``v1_session_key.*``, ``cli.*`` ...) at
runtime, so static analysis alone would miss them. ``collect_all``
bundles the whole library plus its ``cryptography`` dependency.

``points.json`` is bundled inside the exe as a fallback AND copied
next to the exe by the build scripts: the copy next to the exe is
the editable one -- replace its ``symbol`` values with the names
returned by ``--browse`` on the real CPU.
"""

import os

from PyInstaller.utils.hooks import collect_all

SPEC_DIR = os.path.dirname(os.path.abspath(SPEC))
PROJECT_ROOT = os.path.dirname(SPEC_DIR)

tmp_ret = collect_all("s7commplus")
datas = tmp_ret[0]
binaries = tmp_ret[1]
hiddenimports = tmp_ret[2]

datas += [(os.path.join(SPEC_DIR, "points.json"), ".")]
hiddenimports += [
    "cryptography",
    "s7commplus",
    "s7commplus.client",
]

a = Analysis(
    [os.path.join(SPEC_DIR, "__main__.py")],
    pathex=[PROJECT_ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="s7gateway",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
