"""setup.sh: the one-line installer. No network: --help, bad input, --dry-run, a local clone."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / "setup.sh"


def _run(*args: str, cwd: Path, stdin: bool = False) -> subprocess.CompletedProcess:
    if stdin:  # the way `curl ... | bash -s -- ARGS` runs it: no file on disk
        return subprocess.run(["bash", "-s", "--", *args], input=SETUP.read_text(),
                              cwd=cwd, capture_output=True, text=True, timeout=60)
    return subprocess.run(["bash", str(SETUP), *args], cwd=cwd, capture_output=True,
                          text=True, timeout=60)


def test_syntax():
    assert subprocess.run(["bash", "-n", str(SETUP)]).returncode == 0


def test_help_works_when_piped(tmp_path):
    out = _run("--help", cwd=tmp_path, stdin=True)
    assert out.returncode == 0
    assert "--with-system-packages" in out.stdout and "--dry-run" in out.stdout


@pytest.mark.parametrize("args", [("--nope",), ("--models", "huge"), ("--dir",)])
def test_bad_options_exit_1(tmp_path, args):
    out = _run(*args, cwd=tmp_path)
    assert out.returncode == 1 and out.stderr.strip()


def test_dry_run_changes_nothing(tmp_path):
    out = _run("--dry-run", "--models", "none", "--dir", "lab", cwd=tmp_path, stdin=True)
    assert out.returncode == 0, out.stderr
    assert "would run: git clone --recurse-submodules" in out.stdout
    assert "sudo" not in out.stdout  # never without --with-system-packages
    assert list(tmp_path.iterdir()) == []


def test_python_without_venv_is_reported_before_anything_is_cloned(tmp_path):
    """Debian's python3 has no venv module until python3-venv is installed."""
    shadow = tmp_path / "shadow"
    shadow.mkdir()
    (shadow / "ensurepip.py").write_text("raise ImportError('no ensurepip here')\n")
    work = tmp_path / "work"
    work.mkdir()
    out = subprocess.run(["bash", str(SETUP), "--models", "none"], cwd=work, capture_output=True,
                         text=True, timeout=60, env={**os.environ, "PYTHONPATH": str(shadow)})
    assert out.returncode == 1
    assert "venv module" in out.stderr and "python3-venv" in out.stderr
    assert list(work.iterdir()) == []


def test_ps1_and_sh_offer_the_same_options():
    """A rule written twice drifts: both scripts must name the same repo, models and switches."""
    sh, ps1 = SETUP.read_text(), (ROOT / "setup.ps1").read_text()
    for needle in ("https://github.com/nikolareljin/local-ai-lab.git", "qwen3:1.7b", "qwen3.5:4b",
                   "LOCAL_AI_LAB_REPO", "https://console.typesafe.ai/keys"):
        assert needle in sh and needle in ps1, needle
    switches = {"--dir": "$Dir", "--ref": "$Ref", "--models": "$Models", "--dry-run": "$DryRun",
                "--with-system-packages": "$WithSystemPackages"}
    for flag, switch in switches.items():
        assert flag in sh and switch in ps1, flag
    # Windows PowerShell 5.1 misreads UTF-8 without a BOM, so the script stays ASCII.
    assert not [c for c in ps1 if ord(c) > 127]


def _pwsh(*command: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["pwsh", "-NoProfile", *command], cwd=cwd, capture_output=True,
                          text=True, timeout=120)


needs_pwsh = pytest.mark.skipif(shutil.which("pwsh") is None, reason="PowerShell is not installed")


@needs_pwsh
def test_ps1_dry_run(tmp_path):
    out = _pwsh("-File", str(ROOT / "setup.ps1"), "-DryRun", "-Models", "none", "-Dir", "lab",
                cwd=tmp_path)
    assert out.returncode == 0, out.stderr
    assert "would run: git clone --recurse-submodules" in out.stdout
    assert "winget" not in out.stdout  # never without -WithSystemPackages, when the tools exist
    assert list(tmp_path.iterdir()) == []


@needs_pwsh
def test_ps1_piped_into_iex_leaves_the_session_alone(tmp_path):
    """`irm ... | iex` runs in the caller's session: no leaked functions, settings, or exit.

    The clone URL does not exist, so the run fails at step 2; the session must survive that.
    """
    script = (f"$env:LOCAL_AI_LAB_REPO = '{tmp_path / 'nowhere'}'; "
              f"try {{ Get-Content -Raw '{ROOT / 'setup.ps1'}' | Invoke-Expression }} "
              "catch { 'failed' }; "
              "'alive ' + $ErrorActionPreference + ' ' + "
              "[bool](Get-Command Invoke-Step -ErrorAction SilentlyContinue)")
    out = _pwsh("-Command", script, cwd=tmp_path)
    assert out.stdout.strip().endswith("failed\nalive Continue False"), out.stdout + out.stderr
    assert not (tmp_path / "local-ai-lab" / "venv").exists()
