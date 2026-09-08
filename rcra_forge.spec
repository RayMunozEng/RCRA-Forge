# -*- mode: python ; coding: utf-8 -*-
#
# RCRA Forge — PyInstaller build spec
#
# Build command (run from the rcra_forge\ folder):
#   pyinstaller rcra_forge.spec
#
# Output: dist\RCRA_Forge\RCRA_Forge.exe  (folder mode, recommended)
#      or dist\RCRA_Forge.exe              (one-file mode, slower startup)

import sys
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# Collect all PyQt6 plugins (needed for OpenGL, platform, styles)
qt_hidden = collect_submodules('PyQt6')

# Collect imagecodecs — has binary codec extensions that must be bundled
imagecodecs_hidden = collect_submodules('imagecodecs')
imagecodecs_datas  = collect_data_files('imagecodecs')

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        # Include README so it's accessible from Help menu if desired
        ('README.md', '.'),
        ('core/*.glsl', 'core'),
    ] + imagecodecs_datas,
    hiddenimports=[
        # imagecodecs — texture decompression (BC1/BC7 etc.)
        'imagecodecs',
        'imagecodecs._imagecodecs',
    ] + imagecodecs_hidden + [
        # PyQt6 internals
        'PyQt6.QtOpenGL',
        'PyQt6.QtOpenGLWidgets',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        # OpenGL
        'OpenGL',
        'OpenGL.GL',
        'OpenGL.GL.shaders',
        'OpenGL.platform',
        'OpenGL.platform.win32',
        'OpenGL.arrays',
        'OpenGL.arrays.numpymodule',
        # NumPy
        'numpy',
        'numpy.core._multiarray_umath',
        # Pillow
        'PIL',
        'PIL.Image',
        'PIL.ImageFile',
        'PIL._imaging',
        # Our packages
        'core',
        'core.archive',
        'core.mesh',
        'core.texture',
        'core.level',
        'core.skeleton',
        'ui',
        'ui.main_window',
        'ui.asset_browser',
        'ui.viewport',
        'ui.properties_panel',
        'ui.texture_viewer',
        'ui.scene_panel',
        'ui.skeleton_viewer',
        'ui.hex_inspector',
        'exporters',
        'exporters.gltf_exporter',
        'exporters.fbx_exporter',
        'exporters.group_exporter',
        'core.material',
        'core.hashes',
    ] + qt_hidden,
    hookspath=['hooks'],
    hooksconfig={},
    runtime_hooks=['hooks/hook_opengl_fix.py'],
    excludes=[
        # Trim unused heavy packages to reduce size
        'tkinter',
        'matplotlib',
        'scipy',
        'pandas',
        'IPython',
        'jupyter',
        'notebook',
        'PyQt5',
        'PySide2',
        'PySide6',
        'wx',
        'gtk',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ── Folder-mode EXE (recommended — faster startup, easier to update) ──────────
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='RCRA_Forge',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,               # Compress with UPX if available
    console=False,          # No console window (GUI app)
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets\\icon.ico' if sys.platform == 'win32' else None,
    version='version_info.txt',  # Windows version resource (optional)
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='RCRA_Forge',
)

# ── Optional: single-file EXE ─────────────────────────────────────────────────
# Uncomment the block below and comment out the COLLECT block above
# to build a single RCRA_Forge.exe (slower first launch ~5-10s due to unpacking)
#
# exe_onefile = EXE(
#     pyz,
#     a.scripts,
#     a.binaries,
#     a.zipfiles,
#     a.datas,
#     [],
#     name='RCRA_Forge',
#     debug=False,
#     bootloader_ignore_signals=False,
#     strip=False,
#     upx=True,
#     console=False,
#     icon='assets\\icon.ico',
# )
