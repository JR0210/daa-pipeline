"""Integration tests for run_pipeline.py / daa/pipeline.py.

Runs entirely against a synthetic pipeline.yaml with trivial helper scripts
(always-exit-0, exit-2-until-a-marker-file-exists) -- no dependency on R or
the real mesh-processing scripts, so this suite runs anywhere Python does.

Each pipeline action is invoked as a fresh `run_pipeline.py` subprocess
(matching real usage: separate CLI invocations across a research session),
so these tests also exercise state persisting correctly across processes.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from daa.pipeline import load_pipeline

REPO_ROOT = Path(__file__).resolve().parent.parent
RUN_PIPELINE = REPO_ROOT / "run_pipeline.py"


def _write_helper_scripts(scripts_dir: Path) -> tuple[Path, Path]:
    scripts_dir.mkdir(parents=True, exist_ok=True)

    always_ok = scripts_dir / "always_ok.py"
    always_ok.write_text("import sys\nsys.exit(0)\n", encoding="utf-8")

    gate_until_marker = scripts_dir / "gate_until_marker.py"
    gate_until_marker.write_text(
        "import sys, os\n"
        "sys.exit(0 if os.path.exists(sys.argv[1]) else 2)\n",
        encoding="utf-8",
    )

    return always_ok, gate_until_marker


def _write_test_pipeline(tmp_path: Path) -> Path:
    always_ok, gate_until_marker = _write_helper_scripts(tmp_path / "scripts")
    python = sys.executable

    pipeline = {
        "stages": [
            {"name": "step_one", "cmd": [python, str(always_ok)]},
            {
                "name": "step_gate",
                "gate": "exit_code",
                "cmd": [python, str(gate_until_marker), "{data_root}/gate_marker.txt"],
            },
            {"name": "step_two", "cmd": [python, str(always_ok)]},
            {
                "name": "approve_step",
                "gate": "approval",
                "approval_key": "my_approval",
                "message": "approve me: {data_root}",
            },
            {"name": "step_three", "cmd": [python, str(always_ok)]},
            {
                "name": "presence_step",
                "gate": "file_presence",
                "check": "{data_root}/presence_marker.txt",
                "message": "waiting for {data_root}/presence_marker.txt",
            },
            {"name": "step_four", "cmd": [python, str(always_ok)]},
        ]
    }

    pipeline_path = tmp_path / "pipeline.yaml"
    pipeline_path.write_text(yaml.safe_dump(pipeline), encoding="utf-8")
    return pipeline_path


def _run(
    tmp_path: Path,
    pipeline_path: Path,
    *extra_args: str,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    data_root = tmp_path / "data"
    cmd = [
        sys.executable,
        str(RUN_PIPELINE),
        "--data-root",
        str(data_root),
        "--pipeline",
        str(pipeline_path),
        *extra_args,
    ]
    env = {**os.environ, **extra_env} if extra_env else None
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def test_full_run_halts_at_each_gate_and_resumes(tmp_path):
    pipeline_path = _write_test_pipeline(tmp_path)
    data_root = tmp_path / "data"

    # step_one succeeds, step_gate halts (marker absent).
    result = _run(tmp_path, pipeline_path)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "step_gate" in result.stdout
    assert "HALTED" in result.stdout

    status = _run(tmp_path, pipeline_path, "--status")
    assert "[x] step_one" in status.stdout
    assert "[ ] step_gate" in status.stdout

    # Clear the watertightness-style gate by creating the marker file.
    (data_root).mkdir(parents=True, exist_ok=True)
    (data_root / "gate_marker.txt").write_text("ok", encoding="utf-8")

    # Resume: step_gate now passes, step_two runs, halts at the approval gate.
    result = _run(tmp_path, pipeline_path)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "approve_step" in result.stdout
    assert "awaiting approval" in result.stdout

    status = _run(tmp_path, pipeline_path, "--status")
    assert "[x] step_two" in status.stdout
    assert "awaiting --approve" in status.stdout

    # Approve, then resume through step_three to the file_presence gate.
    result = _run(tmp_path, pipeline_path, "--approve", "my_approval")
    assert result.returncode == 0, result.stdout + result.stderr

    result = _run(tmp_path, pipeline_path)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "presence_step" in result.stdout
    assert "waiting on external output" in result.stdout

    # file_presence clears automatically once the file exists -- no approval needed.
    (data_root / "presence_marker.txt").write_text("ok", encoding="utf-8")

    result = _run(tmp_path, pipeline_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Pipeline run complete." in result.stdout

    status = _run(tmp_path, pipeline_path, "--status")
    assert status.stdout.count("[x]") == 7

    # Nothing left to do.
    result = _run(tmp_path, pipeline_path)
    assert result.returncode == 0
    assert "Nothing to do" in result.stdout


def test_only_runs_a_single_stage_regardless_of_order(tmp_path):
    pipeline_path = _write_test_pipeline(tmp_path)

    result = _run(tmp_path, pipeline_path, "--only", "step_three")
    assert result.returncode == 0, result.stdout + result.stderr

    status = _run(tmp_path, pipeline_path, "--status")
    assert "[x] step_three" in status.stdout
    assert "[ ] step_one" in status.stdout
    assert "[ ] step_gate" in status.stdout


def test_from_reenters_at_a_specific_stage(tmp_path):
    pipeline_path = _write_test_pipeline(tmp_path)
    data_root = tmp_path / "data"

    # Starting fresh with --from step_three should skip everything before it
    # and halt at the next unmet gate (presence_step), without ever touching
    # step_one/step_gate/step_two/approve_step.
    result = _run(tmp_path, pipeline_path, "--from", "step_three")
    assert result.returncode == 2, result.stdout + result.stderr

    status = _run(tmp_path, pipeline_path, "--status")
    assert "[x] step_three" in status.stdout
    assert "[ ] step_one" in status.stdout
    assert "[ ] approve_step" in status.stdout

    # Default resume now continues from after step_three -- straight to
    # presence_step -- without needing --from again.
    data_root.mkdir(parents=True, exist_ok=True)
    (data_root / "presence_marker.txt").write_text("ok", encoding="utf-8")

    result = _run(tmp_path, pipeline_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Pipeline run complete." in result.stdout


def test_dry_run_executes_nothing_and_leaves_no_state(tmp_path):
    pipeline_path = _write_test_pipeline(tmp_path)
    data_root = tmp_path / "data"

    result = _run(tmp_path, pipeline_path, "--dry-run")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "would run" in result.stdout
    assert "Dry run complete" in result.stdout
    assert not (data_root / "_reports" / "pipeline_state.json").exists()


def test_status_on_fresh_pipeline_shows_nothing_done(tmp_path):
    pipeline_path = _write_test_pipeline(tmp_path)

    result = _run(tmp_path, pipeline_path, "--status")
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("[ ]") == 7
    assert "[x]" not in result.stdout


def test_requires_file_halts_until_the_setting_points_at_a_real_file(tmp_path):
    always_ok, _ = _write_helper_scripts(tmp_path / "scripts")
    pipeline = {
        "stages": [
            {
                "name": "needs_landmarks",
                "cmd": [sys.executable, str(always_ok)],
                "requires_file": "landmarks_csv",
            },
        ]
    }
    pipeline_path = tmp_path / "pipeline.yaml"
    pipeline_path.write_text(yaml.safe_dump(pipeline), encoding="utf-8")

    # LANDMARKS_CSV unset (or pointing nowhere) -> clear halt, not a raw
    # failure from deep inside whatever script actually needed the file.
    result = _run(tmp_path, pipeline_path, extra_env={"LANDMARKS_CSV": ""})
    assert result.returncode == 2, result.stdout + result.stderr
    assert "required file not set or not found" in result.stdout

    # Pointing it at a real file clears the preflight and the stage runs.
    landmarks_csv = tmp_path / "landmarks.csv"
    landmarks_csv.write_text("id,x.1,y.1,z.1\n", encoding="utf-8")

    result = _run(tmp_path, pipeline_path, extra_env={"LANDMARKS_CSV": str(landmarks_csv)})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Pipeline run complete." in result.stdout


def test_load_pipeline_rejects_non_mapping_root(tmp_path):
    pipeline_path = tmp_path / "pipeline.yaml"
    pipeline_path.write_text(yaml.safe_dump(["not", "a", "mapping"]), encoding="utf-8")

    with pytest.raises(ValueError, match="must be a YAML mapping"):
        load_pipeline(pipeline_path)


def test_load_pipeline_rejects_non_mapping_stage_entry(tmp_path):
    pipeline_path = tmp_path / "pipeline.yaml"
    pipeline_path.write_text(yaml.safe_dump({"stages": ["just_a_string"]}), encoding="utf-8")

    with pytest.raises(ValueError, match="must be a mapping"):
        load_pipeline(pipeline_path)


def test_load_pipeline_rejects_non_list_cmd(tmp_path):
    pipeline_path = tmp_path / "pipeline.yaml"
    pipeline_path.write_text(
        yaml.safe_dump({"stages": [{"name": "bad", "cmd": "python script.py"}]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="cmd must be a list of strings"):
        load_pipeline(pipeline_path)


def test_load_pipeline_rejects_unsupported_foreach(tmp_path):
    pipeline_path = tmp_path / "pipeline.yaml"
    pipeline_path.write_text(
        yaml.safe_dump({"stages": [{"name": "bad", "cmd": ["true"], "foreach": "parts"}]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unsupported foreach value"):
        load_pipeline(pipeline_path)
