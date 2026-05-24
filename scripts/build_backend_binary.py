#!/usr/bin/env python3
"""Build the Codeflow Light backend as a standalone executable."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import venv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
OUTPUT = ROOT / "frontend" / "backend-bin"
BUILD = ROOT / "build" / "pyinstaller-backend"
BUILD_VENV = ROOT / "build" / "backend-binary-venv"
NAME = "codeflow-light-backend"


def executable_name() -> str:
    return f"{NAME}.exe" if platform.system() == "Windows" else NAME


def run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=str(cwd), check=True)


def python_version(python: Path | str) -> tuple[int, int, int]:
    result = subprocess.run(
        [
            str(python),
            "-c",
            "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=True,
    )
    return tuple(int(part) for part in result.stdout.strip().split("."))


def compatible_python() -> str:
    requested = os.environ.get("CODEFLOW_LIGHT_BUILD_PYTHON", "").strip()
    candidates = [
        requested,
        sys.executable,
        "python3.13",
        "python3.12",
        "python3.11",
        "python3",
        "python",
    ]
    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        resolved = shutil.which(candidate) or candidate
        if not Path(resolved).exists():
            continue
        try:
            if python_version(resolved) >= (3, 11, 0):
                return resolved
        except Exception:
            continue
    raise SystemExit(
        "Python 3.11 or newer is required to build the packaged backend. "
        "Set CODEFLOW_LIGHT_BUILD_PYTHON to a compatible Python executable."
    )


def venv_python(venv_dir: Path) -> Path:
    return (
        venv_dir / "Scripts" / "python.exe"
        if platform.system() == "Windows"
        else venv_dir / "bin" / "python"
    )


def ensure_build_python() -> Path:
    python = venv_python(BUILD_VENV)
    if python.exists():
        try:
            if python_version(python) < (3, 11, 0):
                shutil.rmtree(BUILD_VENV)
        except Exception:
            shutil.rmtree(BUILD_VENV)

    if not python.exists():
        print(f"Creating backend build venv: {BUILD_VENV}")
        run([compatible_python(), "-m", "venv", str(BUILD_VENV)], ROOT)

    marker = BUILD_VENV / ".codeflow-light-backend-build-ready"
    if not marker.exists():
        run([str(python), "-m", "pip", "install", "--upgrade", "pip"], ROOT)
        run([str(python), "-m", "pip", "install", "pyinstaller"], ROOT)
        run([str(python), "-m", "pip", "install", str(BACKEND)], ROOT)
        marker.write_text("ready\n", encoding="utf-8")

    return python


def ensure_pyinstaller(python: Path) -> None:
    found = subprocess.run(
        [str(python), "-m", "PyInstaller", "--version"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if found.returncode == 0:
        return

    raise SystemExit(
        "PyInstaller is required to build the packaged backend, but it could not be installed "
        f"in the local build venv at {BUILD_VENV}."
    )


def main() -> int:
    build_python = ensure_build_python()
    ensure_pyinstaller(build_python)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    BUILD.mkdir(parents=True, exist_ok=True)

    target = OUTPUT / executable_name()
    if target.exists():
        target.unlink()

    cmd = [
        str(build_python),
        "-m",
        "PyInstaller",
        "--onefile",
        "--clean",
        "--name",
        NAME,
        "--distpath",
        str(OUTPUT),
        "--workpath",
        str(BUILD / "work"),
        "--specpath",
        str(BUILD / "spec"),
        str(BACKEND / "main.py"),
    ]
    run(cmd, BACKEND)

    if not target.exists():
        raise SystemExit(f"Backend executable was not created: {target}")

    if os.name != "nt":
        target.chmod(target.stat().st_mode | 0o111)

    shutil.rmtree(BUILD / "work", ignore_errors=True)
    print(f"Built backend executable: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
