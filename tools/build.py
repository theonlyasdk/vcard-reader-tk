#!/usr/bin/env python
"""Build a standalone vcard-reader executable with PyInstaller.

Usage: python tools/build.py [--clean]

Output: dist/vcard-reader.exe (Windows) — gitignored, attach to a release.
"""

import shutil
import subprocess
import sys
from pathlib import Path


def ensure_pyinstaller():
    try:
        import PyInstaller  # noqa: F401
        print("PyInstaller present")
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"],
                       check=True)


def main():
    root = Path(__file__).resolve().parent.parent
    ensure_pyinstaller()
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=vcard-reader",
        "--onefile",
        "--windowed",
        "--clean",
        "--noconfirm",
        f"--paths={root / 'src'}",
        str(root / "vcard_reader.py"),
    ]
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=root)
    exe = root / "dist" / ("vcard-reader.exe" if sys.platform.startswith("win")
                           else "vcard-reader")
    if exe.exists():
        print(f"Built: {exe} ({exe.stat().st_size / 1024 / 1024:.1f} MB)")
    else:
        print(f"Expected output missing: {exe}")
        sys.exit(1)
    if "--clean" in sys.argv:
        shutil.rmtree(root / "build", ignore_errors=True)
        (root / "vcard-reader.spec").unlink(missing_ok=True)
        print("Cleaned build artifacts")


if __name__ == "__main__":
    main()
