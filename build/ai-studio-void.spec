# PyInstaller spec — AI Studio Void (pywebview shell + engine)
# Build:  pyinstaller build/ai-studio-void.spec --noconfirm --distpath dist
# onedir on purpose: fast start, AV-friendly, inspectable when frozen assets misbehave.
from PyInstaller.utils.hooks import collect_data_files, copy_metadata

block_cipher = None

a = Analysis(
    ["../main.py"],
    pathex=[".."],
    binaries=[],
    datas=[
        ("../web", "web"),
        ("../engine/fal_models.json", "engine"),
        ("../config.default.json", "."),
        ("../ai-studio-void.ico", "."),
        ("../placeholder.png", "."),
    ] + collect_data_files("webview")
      # these read their own version via importlib.metadata at import — bundle dist-info
      + copy_metadata("replicate") + copy_metadata("fal-client") + copy_metadata("huggingface_hub"),
    hiddenimports=[
        "webview.platforms.edgechromium",  # WebView2 backend — lazy import PyInstaller can miss
        "webview.platforms.winforms",
        "clr_loader", "pythonnet",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["customtkinter", "tkinterdnd2"],  # gone with the CTk UI
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="AI Studio Void",
    debug=False, strip=False, upx=False,
    console=False,
    icon="../ai-studio-void.ico",
)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas,
               strip=False, upx=False, name="AI Studio Void")
