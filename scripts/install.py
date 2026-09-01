#!/usr/bin/env python3
"""
Interactive installation script for de-drum.

Checks for required dependencies, verifies versions, and installs missing components
with user confirmation.
"""

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional


REQUIREMENTS = {
    "python": {"min_version": (3, 14), "cmd": "python3"},
    "node": {"min_version": (24,), "cmd": "node"},
    "ffmpeg": {"min_version": None, "cmd": "ffmpeg"},
    "yt-dlp": {"min_version": None, "cmd": "yt-dlp"},
}

VENV_DIR = ".venv"
REQUIREMENTS_TXT = "requirements.txt"


def run_cmd(cmd: list[str], capture: bool = True) -> tuple[int, str, str]:
    """Run a command and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            check=False,
        )
        stdout = result.stdout.strip() if result.stdout else ""
        stderr = result.stderr.strip() if result.stderr else ""
        return result.returncode, stdout, stderr
    except FileNotFoundError:
        return 127, "", "command not found"


def parse_version(version_str: str) -> tuple[int, ...]:
    """Extract version tuple from a version string."""
    import re
    match = re.search(r"(\d+(?:\.\d+)+)", version_str)
    if not match:
        return ()
    return tuple(map(int, match.group(1).split(".")))


def check_version(current: tuple[int, ...], minimum: tuple[int, ...]) -> bool:
    """Check if current version meets minimum requirement."""
    if not current or not minimum:
        return True
    # Pad shorter tuple with zeros for comparison
    max_len = max(len(current), len(minimum))
    current_padded = current + (0,) * (max_len - len(current))
    minimum_padded = minimum + (0,) * (max_len - len(minimum))
    return current_padded >= minimum_padded


def check_python() -> tuple[bool, str, tuple[int, ...]]:
    """Check Python version."""
    rc, out, _ = run_cmd(["python3", "--version"])
    if rc != 0:
        return False, "python3 not found", ()
    version = parse_version(out)
    ok = check_version(version, REQUIREMENTS["python"]["min_version"])
    return ok, out, version


def check_node() -> tuple[bool, str, tuple[int, ...]]:
    """Check Node.js version."""
    rc, out, _ = run_cmd(["node", "--version"])
    if rc != 0:
        return False, "node not found", ()
    version = parse_version(out)
    ok = check_version(version, REQUIREMENTS["node"]["min_version"])
    return ok, out, version


def check_tool(name: str) -> tuple[bool, str]:
    """Check if a command-line tool is available."""
    cmd = REQUIREMENTS[name]["cmd"]
    # Use shutil.which first (respects PATH)
    if not shutil.which(cmd):
        return False, f"{name} not found"
    # Try running --version (some tools like ffmpeg output to stderr)
    rc, out, err = run_cmd([cmd, "--version"])
    output = out or err
    if rc == 0 or output:  # ffmpeg returns non-zero but outputs version to stderr
        return True, output.splitlines()[0] if output else "found"
    return False, f"{name} not found"


def check_venv() -> bool:
    """Check if virtual environment exists."""
    return Path(VENV_DIR).exists()


def check_pip_deps() -> tuple[bool, list[str]]:
    """Check if Python dependencies are installed in venv."""
    if not check_venv():
        return False, ["venv not created"]
    pip = str(Path(VENV_DIR) / "bin" / "pip")
    if platform.system() == "Windows":
        pip = str(Path(VENV_DIR) / "Scripts" / "pip.exe")
    req_path = Path(REQUIREMENTS_TXT)
    if not req_path.exists():
        return False, ["requirements.txt not found"]
    # Quick check: try importing key packages
    python = str(Path(VENV_DIR) / "bin" / "python")
    if platform.system() == "Windows":
        python = str(Path(VENV_DIR) / "Scripts" / "python.exe")
    rc, _, _ = run_cmd([python, "-c", "import torch, demucs, rich, torchcodec"])
    if rc != 0:
        return False, ["some Python deps missing"]
    return True, []


def prompt_yes_no(question: str, default: bool = True) -> bool:
    """Prompt user for yes/no confirmation."""
    default_str = "Y/n" if default else "y/N"
    while True:
        try:
            response = input(f"{question} [{default_str}]: ").strip().lower()
            if not response:
                return default
            if response in ("y", "yes"):
                return True
            if response in ("n", "no"):
                return False
            print("Please answer 'y' or 'n'.")
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            sys.exit(1)


def install_system_deps() -> bool:
    """Install system dependencies via Homebrew (macOS) or apt (Linux)."""
    system = platform.system()
    if system == "Darwin":
        # macOS - use Homebrew
        if not shutil.which("brew"):
            print("Homebrew not found. Please install from https://brew.sh")
            return False
        print("Installing ffmpeg and yt-dlp via Homebrew...")
        rc, _, err = run_cmd(["brew", "install", "ffmpeg", "yt-dlp"], capture=False)
        return rc == 0
    elif system == "Linux":
        # Try apt (Debian/Ubuntu)
        if shutil.which("apt"):
            print("Installing ffmpeg and yt-dlp via apt...")
            rc, _, _ = run_cmd(["sudo", "apt", "update"], capture=False)
            if rc != 0:
                return False
            rc, _, _ = run_cmd(["sudo", "apt", "install", "-y", "ffmpeg", "yt-dlp"], capture=False)
            return rc == 0
        print("Unsupported Linux distribution. Please install ffmpeg and yt-dlp manually.")
        return False
    else:
        print(f"Automatic system dependency installation not supported on {system}.")
        print("Please install ffmpeg and yt-dlp manually.")
        return False


def create_venv() -> bool:
    """Create Python virtual environment."""
    print(f"Creating virtual environment at {VENV_DIR}/...")
    rc, _, _ = run_cmd([sys.executable, "-m", "venv", VENV_DIR], capture=False)
    return rc == 0


def install_python_deps() -> bool:
    """Install Python dependencies in virtual environment."""
    pip = str(Path(VENV_DIR) / "bin" / "pip")
    if platform.system() == "Windows":
        pip = str(Path(VENV_DIR) / "Scripts" / "pip.exe")

    print("Upgrading pip...")
    rc, _, _ = run_cmd([pip, "install", "--upgrade", "pip", "-q"], capture=False)
    if rc != 0:
        return False

    print("Installing Python dependencies...")
    rc, _, _ = run_cmd([pip, "install", "-r", REQUIREMENTS_TXT, "-q"], capture=False)
    return rc == 0


def run_check() -> bool:
    """Run the environment check."""
    print("\nVerifying installation...")
    python = str(Path(VENV_DIR) / "bin" / "python")
    if platform.system() == "Windows":
        python = str(Path(VENV_DIR) / "Scripts" / "python.exe")
    rc, _, _ = run_cmd([python, "src/separate.py", "--check"], capture=False)
    return rc == 0


def main():
    parser = argparse.ArgumentParser(description="Interactive de-drum installer")
    parser.add_argument("--yes", "-y", action="store_true", help="Assume yes to all prompts")
    parser.add_argument("--skip-system", action="store_true", help="Skip system dependency installation")
    parser.add_argument("--skip-venv", action="store_true", help="Skip venv creation (assume existing)")
    args = parser.parse_args()

    print("=" * 60)
    print("de-drum Interactive Installer")
    print("=" * 60)

    # Check Python
    print("\n[1/6] Checking Python...")
    py_ok, py_ver, py_version = check_python()
    status = "✓" if py_ok else "✗"
    print(f"  {status} Python: {py_ver}")
    if not py_ok:
        print(f"  Required: Python {REQUIREMENTS['python']['min_version']}+")
        if not args.yes:
            print("Please install Python 3.14+ and re-run.")
            sys.exit(1)

    # Check Node
    print("\n[2/6] Checking Node.js...")
    node_ok, node_ver, node_version = check_node()
    status = "✓" if node_ok else "✗"
    print(f"  {status} Node.js: {node_ver}")
    if not node_ok:
        print(f"  Required: Node.js {REQUIREMENTS['node']['min_version']}+")
        if not args.yes:
            print("Please install Node.js 24+ and re-run.")
            sys.exit(1)

    # Check system tools
    print("\n[3/6] Checking system tools...")
    ffmpeg_ok, ffmpeg_ver = check_tool("ffmpeg")
    ytdlp_ok, ytdlp_ver = check_tool("yt-dlp")
    print(f"  {'✓' if ffmpeg_ok else '✗'} ffmpeg: {ffmpeg_ver}")
    print(f"  {'✓' if ytdlp_ok else '✗'} yt-dlp: {ytdlp_ver}")

    need_system = not (ffmpeg_ok and ytdlp_ok)
    if need_system and not args.skip_system:
        if args.yes or prompt_yes_no("Install missing system dependencies (ffmpeg, yt-dlp)?"):
            if not install_system_deps():
                print("Failed to install system dependencies.")
                sys.exit(1)
            # Re-check
            ffmpeg_ok, ffmpeg_ver = check_tool("ffmpeg")
            ytdlp_ok, ytdlp_ver = check_tool("yt-dlp")
            print(f"  {'✓' if ffmpeg_ok else '✗'} ffmpeg: {ffmpeg_ver}")
            print(f"  {'✓' if ytdlp_ok else '✗'} yt-dlp: {ytdlp_ver}")

    # Check virtual environment
    print("\n[4/6] Checking virtual environment...")
    venv_exists = check_venv()
    print(f"  {'✓' if venv_exists else '✗'} .venv/: {'exists' if venv_exists else 'not found'}")

    need_venv = not venv_exists
    if need_venv and not args.skip_venv:
        if args.yes or prompt_yes_no("Create virtual environment?"):
            if not create_venv():
                print("Failed to create virtual environment.")
                sys.exit(1)
            print("  ✓ Virtual environment created")

    # Check Python dependencies
    print("\n[5/6] Checking Python dependencies...")
    deps_ok, missing = check_pip_deps()
    print(f"  {'✓' if deps_ok else '✗'} Python deps: {'installed' if deps_ok else ', '.join(missing)}")

    if not deps_ok:
        if args.yes or prompt_yes_no("Install Python dependencies?"):
            if not install_python_deps():
                print("Failed to install Python dependencies.")
                sys.exit(1)
            print("  ✓ Python dependencies installed")

    # Final verification
    print("\n[6/6] Running environment check...")
    if run_check():
        print("\n" + "=" * 60)
        print("Installation complete! ✓")
        print("=" * 60)
        print("\nNext steps:")
        print("  npm run dedrum -- \"https://youtube.com/watch?v=...\"")
        print("  npm run dedrum -- path/to/song.mp3")
    else:
        print("\nEnvironment check failed. Please review the output above.")
        sys.exit(1)


if __name__ == "__main__":
    main()