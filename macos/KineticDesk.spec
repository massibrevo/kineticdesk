import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_dynamic_libs

root = Path(SPECPATH).parent
analysis = Analysis(
    [str(root / "macos/app.py")],
    pathex=[str(root / "backend")],
    binaries=collect_dynamic_libs("mediapipe"),
    datas=[
        (str(root / "frontend/dist"), "studio"),
        (str(root / ".cache/models/hand_landmarker.task"), "models"),
        (str(root / "backend/kineticdesk/replay_poses.json"), "kineticdesk"),
    ],
    hiddenimports=[
        "uvicorn.loops.asyncio",
        "uvicorn.lifespan.on",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.websockets.websockets_impl",
    ],
    hooksconfig={"matplotlib": {"backends": ["Agg"]}},
    excludes=["tkinter", "pytest", "IPython", "jupyter", "notebook", "PyQt6", "PySide6"],
)
archive = PYZ(analysis.pure)
exe = EXE(
    archive, analysis.scripts, [], exclude_binaries=True,
    name="KineticDesk", console=False, upx=False,
    codesign_identity=os.environ.get("KINETICDESK_SIGNING_IDENTITY") or None,
)
files = COLLECT(exe, analysis.binaries, analysis.datas, name="KineticDesk", upx=False)
app = BUNDLE(
    files,
    name="KineticDesk.app",
    icon=str(root / "macos/KineticDesk.icns"),
    bundle_identifier="io.github.massibrevo.kineticdesk",
    version="0.2.0",
    info_plist={
        "CFBundleDisplayName": "KineticDesk",
        "CFBundleVersion": "5",
        "LSMinimumSystemVersion": "13.0",
        "LSMultipleInstancesProhibited": True,
        "NSCameraUsageDescription": "KineticDesk usa la fotocamera per seguire i gesti della mano sul Mac.",
        "NSAppTransportSecurity": {
            "NSAllowsLocalNetworking": True,
            "NSExceptionDomains": {"127.0.0.1": {"NSExceptionAllowsInsecureHTTPLoads": True}},
        },
        "NSHighResolutionCapable": True,
        "WKAppBoundDomains": ["127.0.0.1"],
    },
)
