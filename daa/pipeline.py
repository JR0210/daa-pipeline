"""The Stage 2 pipeline engine: loads pipeline.yaml, tracks progress in a
small state file, and runs stages in order -- stopping cleanly at whichever
of the three README gates (watertightness, visual QC, Deformetrica) needs a
human, and resuming past it once that's been dealt with.

Design notes (see docs/plan for the full rationale):
  - Only the visual QC gate needs an explicit human approval
    (`run_pipeline.py --approve visual_qc`). Watertightness self-clears
    (fix the mesh, re-run, the gate either still fires or it doesn't).
    Deformetrica is detected by checking whether its output files exist.
  - Stages are invoked via subprocess with an argv list (never a shell
    string), so paths containing spaces -- like DATA_ROOT itself -- are
    never mis-parsed.
  - Resume tracks stage-level completion only. Fine-grained "skip this file
    if it already exists" stays where it already lives: each script's own
    --overwrite logic.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

from daa.config import STAGE_DIRS, Settings

# Stage commands reference scripts by relative path (e.g. "measure_vol.py",
# "ascii_alignment.r"), so subprocesses are always launched with this as
# their cwd -- otherwise they'd only resolve when run_pipeline.py happens
# to be invoked from the repo root.
REPO_ROOT = Path(__file__).resolve().parent.parent

CONTINUE = "continue"
HALTED = "halted"

VALID_GATES = {None, "exit_code", "approval", "file_presence"}


@dataclass
class StageSpec:
    name: str
    cmd: list[str] | None = None
    foreach: str | None = None
    gate: str | None = None
    approval_key: str | None = None
    check: str | None = None
    message: str | None = None
    requires_binary: str | None = None
    requires_file: str | None = None


def load_pipeline(path: Path) -> list[StageSpec]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must be a YAML mapping with a top-level 'stages' key, got {type(raw).__name__}")

    stage_entries = raw.get("stages") or []
    if not stage_entries:
        raise ValueError(f"No stages defined in {path}")

    stages: list[StageSpec] = []
    seen: set[str] = set()
    for entry in stage_entries:
        if not isinstance(entry, dict):
            raise ValueError(f"Stage entry in {path} must be a mapping, got {type(entry).__name__}: {entry!r}")

        name = entry.get("name")
        if not name:
            raise ValueError(f"Stage entry missing 'name' in {path}: {entry}")
        if name in seen:
            raise ValueError(f"Duplicate stage name in {path}: {name}")
        seen.add(name)

        gate = entry.get("gate")
        if gate not in VALID_GATES:
            raise ValueError(f"Stage {name!r} has unknown gate type: {gate!r}")
        if gate == "approval" and not entry.get("approval_key"):
            raise ValueError(f"Stage {name!r} has gate: approval but no approval_key")
        if gate == "file_presence" and not entry.get("check"):
            raise ValueError(f"Stage {name!r} has gate: file_presence but no check")
        if gate not in ("approval", "file_presence"):
            cmd = entry.get("cmd")
            if not cmd:
                raise ValueError(f"Stage {name!r} has no cmd and is not an approval/file_presence gate")
            if not isinstance(cmd, list) or not all(isinstance(tok, str) for tok in cmd):
                raise ValueError(f"Stage {name!r} cmd must be a list of strings, got: {cmd!r}")

        foreach = entry.get("foreach")
        if foreach not in (None, "part"):
            raise ValueError(f"Stage {name!r} has unsupported foreach value: {foreach!r} (only 'part' is supported)")

        stages.append(
            StageSpec(
                name=name,
                cmd=entry.get("cmd"),
                foreach=entry.get("foreach"),
                gate=gate,
                approval_key=entry.get("approval_key"),
                check=entry.get("check"),
                message=entry.get("message"),
                requires_binary=entry.get("requires_binary"),
                requires_file=entry.get("requires_file"),
            )
        )
    return stages


@dataclass
class PipelineState:
    completed: list[str] = field(default_factory=list)
    approvals: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "PipelineState":
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls()
        return cls(
            completed=list(data.get("completed", [])),
            approvals=dict(data.get("approvals", {})),
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"completed": self.completed, "approvals": self.approvals}, indent=2),
            encoding="utf-8",
        )

    def is_completed(self, name: str) -> bool:
        return name in self.completed

    def mark_completed(self, name: str) -> None:
        if name not in self.completed:
            self.completed.append(name)

    def approve(self, key: str, timestamp: str | None = None) -> None:
        self.approvals[key] = timestamp or datetime.now(timezone.utc).isoformat()


def build_context(settings: Settings) -> dict[str, str]:
    context = {
        "python": sys.executable,
        "data_root": str(settings.data_root),
        "jobs": str(max(1, settings.jobs)),
        "rscript_path": settings.rscript_path,
        "landmarks_csv": str(settings.landmarks_csv) if settings.landmarks_csv else "",
        "reports_dir": str(settings.reports_dir()),
    }
    for stage_key in STAGE_DIRS:
        context[f"{stage_key}_dir"] = str(settings.stage_dir(stage_key))
    return context


def _parts_for(stage: StageSpec) -> list[str | None]:
    return ["crania", "mandible"] if stage.foreach == "part" else [None]


def _stage_context(context: dict[str, str], part: str | None) -> dict[str, str]:
    if part is None:
        return context
    ctx = dict(context)
    ctx["part"] = part
    return ctx


def preview_stage(stage: StageSpec, context: dict[str, str]) -> None:
    """Print what a stage would do without running/checking/halting anything."""
    if stage.gate == "approval":
        print(f"[{stage.name}] (approval gate) would check approval key {stage.approval_key!r}")
        return

    if stage.gate == "file_presence":
        for part in _parts_for(stage):
            ctx = _stage_context(context, part)
            label = f" [{part}]" if part else ""
            print(f"[{stage.name}]{label} would check for: {stage.check.format(**ctx)}")
        return

    for part in _parts_for(stage):
        ctx = _stage_context(context, part)
        argv = [tok.format(**ctx) for tok in stage.cmd]
        label = f" [{part}]" if part else ""
        print(f"[{stage.name}]{label} would run: {' '.join(argv)}")


def _binary_available(binary: str) -> bool:
    return bool(shutil.which(binary)) or Path(binary).is_file()


def _run_cmd_stage(stage: StageSpec, settings: Settings, context: dict[str, str], verbose: bool) -> str:
    if stage.requires_binary:
        binary = getattr(settings, stage.requires_binary, None)
        if not binary or not _binary_available(binary):
            print(f"[{stage.name}] HALTED - required binary not found: {stage.requires_binary}={binary!r}")
            print(f"  Set {stage.requires_binary.upper()} in .env to a valid executable path.")
            return HALTED

    if stage.requires_file:
        value = context.get(stage.requires_file, "")
        if not value or not Path(value).is_file():
            print(f"[{stage.name}] HALTED - required file not set or not found: {stage.requires_file}={value!r}")
            print(f"  Set {stage.requires_file.upper()} in .env to a valid file path.")
            return HALTED

    for part in _parts_for(stage):
        ctx = _stage_context(context, part)
        argv = [tok.format(**ctx) for tok in stage.cmd]
        label = f"{stage.name}" + (f" [{part}]" if part else "")

        if verbose:
            print(f"[{label}] running: {' '.join(argv)}")

        result = subprocess.run(argv, cwd=REPO_ROOT)
        code = result.returncode

        if code == 0:
            continue
        if code == 2:
            note = " -- this is a self-clearing gate: fix the issue and re-run" if stage.gate == "exit_code" else ""
            print(f"[{label}] HALTED - exit code 2 (gate).{note}")
            return HALTED
        if code == 3:
            print(
                f"[{label}] WARNING - partial success (exit code 3). "
                f"Some specimens errored -- check {context['reports_dir']} for this stage's *_errors.csv. Continuing."
            )
            continue
        print(f"[{label}] HALTED - exit code {code}.")
        return HALTED

    return CONTINUE


def _run_approval_gate(stage: StageSpec, state: PipelineState, context: dict[str, str]) -> str:
    if stage.approval_key in state.approvals:
        return CONTINUE
    print(f"[{stage.name}] HALTED - awaiting approval:")
    msg = stage.message.format(**context) if stage.message else (
        f"Run: python run_pipeline.py --approve {stage.approval_key}"
    )
    print(f"  {msg}")
    return HALTED


def _run_file_presence_gate(stage: StageSpec, context: dict[str, str]) -> str:
    missing: list[tuple[str | None, dict[str, str]]] = []
    for part in _parts_for(stage):
        ctx = _stage_context(context, part)
        if not Path(stage.check.format(**ctx)).exists():
            missing.append((part, ctx))

    if not missing:
        return CONTINUE

    print(f"[{stage.name}] HALTED - waiting on external output:")
    for part, ctx in missing:
        label = f" ({part})" if part else ""
        msg = stage.message.format(**ctx) if stage.message else f"missing: {stage.check.format(**ctx)}"
        print(f"  {msg}{label}")
    return HALTED


def execute_stage(stage: StageSpec, settings: Settings, state: PipelineState, context: dict[str, str], verbose: bool) -> str:
    if stage.gate == "approval":
        return _run_approval_gate(stage, state, context)
    if stage.gate == "file_presence":
        return _run_file_presence_gate(stage, context)
    return _run_cmd_stage(stage, settings, context, verbose)


def list_status(stages: list[StageSpec], state: PipelineState) -> str:
    lines = []
    for stage in stages:
        done = state.is_completed(stage.name)
        marker = "[x]" if done else "[ ]"
        extra = ""
        if stage.gate == "approval":
            if stage.approval_key in state.approvals:
                extra = f" (approved {state.approvals[stage.approval_key]})"
            else:
                extra = " (awaiting --approve)"
        elif stage.gate == "file_presence":
            extra = " (waiting on external output)" if not done else ""
        lines.append(f"{marker} {stage.name}{extra}")
    return "\n".join(lines)


def run(
    stages: list[StageSpec],
    settings: Settings,
    state: PipelineState,
    state_path: Path,
    from_stage: str | None = None,
    only: str | None = None,
    dry_run: bool = False,
    verbose: bool = False,
) -> int:
    context = build_context(settings)
    names = [s.name for s in stages]

    if only:
        if only not in names:
            print(f"Unknown stage: {only!r}. Known stages: {', '.join(names)}", file=sys.stderr)
            return 1
        selected = [s for s in stages if s.name == only]
    else:
        if from_stage:
            if from_stage not in names:
                print(f"Unknown stage: {from_stage!r}. Known stages: {', '.join(names)}", file=sys.stderr)
                return 1
            start_index = names.index(from_stage)
        else:
            # Resume after the highest-index completed stage, not the first
            # gap from the start -- otherwise a deliberate --from jump ahead
            # (which only marks the stages it actually ran as completed)
            # would be forgotten on the next plain resume and re-run from
            # scratch. In the ordinary sequential case these are equivalent.
            start_index = 0
            for i, s in enumerate(stages):
                if state.is_completed(s.name):
                    start_index = i + 1
        selected = stages[start_index:]

    if not selected:
        print("Nothing to do -- all stages already completed. See --status.")
        return 0

    if dry_run:
        for stage in selected:
            preview_stage(stage, context)
        print("\nDry run complete -- no commands were executed, no state was changed.")
        return 0

    for stage in selected:
        outcome = execute_stage(stage, settings, state, context, verbose)
        if outcome == HALTED:
            return 2
        state.mark_completed(stage.name)
        state.save(state_path)
        print(f"[{stage.name}] done.")

    print("Pipeline run complete." if not only else f"Stage {only!r} complete.")
    return 0
