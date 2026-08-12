"""Unit tests for scripts/rvc_infer.py import-path hardening."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import rvc_infer  # noqa: E402


def test_env_with_rvc_path_prepends():
    root = Path("/tmp/fake-rvc-root")
    env = rvc_infer._env_with_rvc_path({"PYTHONPATH": "/other/lib", "FOO": "1"}, root)
    parts = env["PYTHONPATH"].split(os.pathsep)
    assert parts[0] == str(root)
    assert "/other/lib" in parts
    assert env["FOO"] == "1"


def test_env_with_rvc_path_empty_pythonpath():
    root = Path("/tmp/fake-rvc-root")
    env = rvc_infer._env_with_rvc_path({}, root)
    assert env["PYTHONPATH"] == str(root)


def test_build_rvc_cmd_uses_module_invocation():
    cmd = rvc_infer.build_rvc_cmd(
        python="/venv-rvc/bin/python",
        model=Path("/weights/narrator.pth"),
        src=Path("/tmp/in.wav"),
        dst=Path("/tmp/out.wav"),
        f0_method="rmvpe",
        pitch=0,
        index_args=["--index-rate", "0"],
    )
    assert cmd[:3] == ["/venv-rvc/bin/python", "-m", "infer.cli"]
    assert "infer/cli.py" not in " ".join(cmd)


def test_main_passes_pythonpath_and_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    rvc_root = tmp_path / "RVC"
    (rvc_root / "infer").mkdir(parents=True)
    (rvc_root / "infer" / "cli.py").write_text("# stub\n", encoding="utf-8")
    model = tmp_path / "narrator.pth"
    model.write_bytes(b"x")
    src = tmp_path / "in.wav"
    src.write_bytes(b"RIFF" + b"\x00" * 100)
    dst = tmp_path / "out.wav"

    captured: dict = {}

    def fake_run(cmd, cwd=None, env=None, **kwargs):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        captured["env"] = env
        Path(dst).write_bytes(b"RIFF" + b"\x00" * 100)

        class P:
            returncode = 0

        return P()

    monkeypatch.setenv("LOKALREADER_RVC_ROOT", str(rvc_root))
    monkeypatch.setattr(rvc_infer.subprocess, "run", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "rvc_infer.py",
            "--model",
            str(model),
            "--input",
            str(src),
            "--output",
            str(dst),
        ],
    )

    rc = rvc_infer.main()
    assert rc == 0
    assert captured["cwd"] == str(rvc_root.resolve())
    assert captured["cmd"][:3] == [sys.executable, "-m", "infer.cli"]
    assert captured["env"]["PYTHONPATH"].split(os.pathsep)[0] == str(rvc_root.resolve())
