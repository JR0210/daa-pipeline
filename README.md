# Setup

```
python -m venv .venv

# Windows (PowerShell)
.venv\Scripts\Activate.ps1
# Windows (cmd)
.venv\Scripts\activate.bat
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env   # then edit DATA_ROOT, RSCRIPT_PATH, LANDMARKS_CSV, etc.
```

If PowerShell blocks `Activate.ps1` with an execution-policy error, run
`Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` first and try
again. Activation is a convenience, not a requirement — every script and
`run_pipeline.py` work fine invoked directly via the venv's own
interpreter without activating at all: `.venv\Scripts\python.exe script.py`
on Windows, `.venv/bin/python script.py` on macOS/Linux. `run_pipeline.py`
in particular always uses the interpreter that launched it for every
Python stage, so an unactivated venv is never silently shadowed by a
different `python` on `PATH`.

`.venv` is already gitignored.

## Adding your meshes

Put your wrapped `.ply` meshes directly in `DATA_ROOT`, or in
`DATA_ROOT/01_raw` if you'd rather keep them separate from other files —
the pipeline finds either automatically, no folder needs to be created by
hand. Everything else (`02_decimated` onward) is generated for you as the
pipeline runs.

## Setting up R

Only needed for the `ascii_alignment.r` stage.

- Install R from https://cran.r-project.org if you don't already have it.
- Find `Rscript`'s path:
  - **Windows**: typically
    `C:\Program Files\R\R-<version>\bin\Rscript.exe` (or `...\bin\x64\...`
    on some installs). If R's `bin` folder is already on `PATH`, `where
    Rscript` will find it.
  - **macOS**: `which Rscript` — typically `/usr/local/bin/Rscript`
    (Intel/Homebrew) or `/opt/homebrew/bin/Rscript` (Apple Silicon
    Homebrew).
  - **Linux**: `which Rscript` — typically `/usr/bin/Rscript`.
- Verify it before touching `.env`: `Rscript --version` should print a
  version, not "command not found".
- Install the R packages `ascii_alignment.r` needs, once, from an R
  console: `install.packages(c("Morpho", "geomorph", "abind", "rgl",
  "Rvcg"))`.
- Set `RSCRIPT_PATH` in `.env` to `Rscript` if it resolved via `PATH`
  above, otherwise the full path you found. `run_pipeline.py` checks this
  before running the R stage and halts with a clear message if it's wrong,
  rather than failing inside a subprocess.

Every script now takes CLI flags instead of a hardcoded path at the top of
the file. Run any script with `--help` to see its options. Common flags
across all scripts: `--data-root`, `--part {crania,mandible,both}`,
`--input`, `--output`, `--jobs`, `--overwrite`, `--dry-run`, `-v`.

Scripts skip work whose output already exists unless you pass `--overwrite`,
so the whole pipeline is safe to re-run after fixing a problem partway
through.

# Order of Operations (automated)

`run_pipeline.py` runs every stage below in order and stops only where a
human actually has to do something: rework a non-watertight mesh, look at
the alignment QC images, or run Deformetrica externally. Everything else
runs unattended.

```
python run_pipeline.py
```

The first run will typically stop a few times as you work through it:

```
python run_pipeline.py             # runs until the first thing needing you
# non-watertight mesh(es) found -> rework them, then:
python run_pipeline.py             # resumes automatically, re-checks, continues
# ...
# halts at the visual QC gate:
python run_pipeline.py --approve visual_qc
python run_pipeline.py             # continues to xml/csv manifest generation
# halts waiting on Deformetrica output:
#   (run Deformetrica externally on 06_manifests/<part>/data_set.xml,
#    output to 08_daa/<part>/)
python run_pipeline.py             # detects the output and finishes with kPCA

python run_pipeline.py --status    # check progress at any point
python run_pipeline.py --dry-run   # preview every stage's command, run nothing
```

Only the visual QC gate needs an explicit approval — watertightness
self-clears (fix the mesh, re-run) and the Deformetrica gate is detected
automatically by checking for its output files. See `pipeline.yaml` for the
full stage list and `--from STAGE` / `--only STAGE` to re-enter or re-run a
specific stage.

## Running a stage manually / debugging

Each stage is also just a normal script, useful when diagnosing one stage
in isolation:

```
python measure_vol.py --stage raw --require-watertight
python decimate.py --part both
python measure_vol.py --stage decimated --part both --require-watertight --report-name measure_vol_decimated
python ply_to_ascii.py --part both
Rscript ascii_alignment.r --input <ascii_dir>/crania --landmarks <landmarks_csv> --output <aligned_dir>/crania --part crania
Rscript ascii_alignment.r --input <ascii_dir>/mandible --landmarks <landmarks_csv> --output <aligned_dir>/mandible --part mandible
python ply_to_vtk.py --part both
python vtk_viewer.py --part both   # renders six-view QC images, no window shown -- review 07_qc_images/
python xml_generator.py --part both
python csv_generator.py --part both
# --- run Deformetrica externally on 06_manifests/<part>/data_set.xml, output to 08_daa/<part>/ ---
python kpca_generator.py --part both
```

`ascii_alignment.r` is run once per part since the pipeline's directory
layout keeps crania and mandible fully separate from decimation onward.
`--report-name` keeps the two `measure_vol.py` runs' reports from
overwriting each other under `_reports/` — `run_pipeline.py` already sets
this for you. `--stage` tells `measure_vol.py` which folder(s) to check —
`raw` (the default) and `decimated` look in different places, since
decimated output is already split into per-part folders and raw meshes
aren't.

## New features/changes required

**Status (Stage 1, complete):** decimate now copies through sub-threshold
meshes with canonical `Genus_species_<part>_dec.ply` naming and splits
crania/mandible automatically; every script takes CLI args with settings
in `.env`/`.env.example`; `vtk_viewer.py` renders offscreen with no window
or blocking; `.gitignore` excludes `meshes/` and all pipeline output dirs;
and a set of real bugs (see `daa/`, script docstrings, and `ascii_alignment.r`
comments for specifics) that either crashed on current dependency versions
or silently produced wrong output have been fixed.

**Status (Stage 2, complete):** `run_pipeline.py` + `pipeline.yaml` now run
every stage above end-to-end, halting only at the one gate that genuinely
needs a human (visual alignment QC — approved with `--approve visual_qc`);
watertightness and the Deformetrica handoff are detected automatically and
self-clear. See "Order of Operations (automated)" above.
`ascii_alignment.r`'s real execution and a real Deformetrica run were not
verified on this machine (no R installed here) — verify those on a machine
that has R before trusting them on real data.

**Status (onboarding fixes, complete):** the pipeline no longer requires
`DATA_ROOT/01_raw` to be created by hand — see "Adding your meshes" above.
Also fixed: `measure_vol.py --stage decimated` (used by the
`measure_vol_decimated` pipeline stage) was silently ignoring `--part` and
re-checking the raw folder a second time instead of the actual decimated
output, meaning the watertightness gate never verified decimation didn't
break anything. It now scans `02_decimated/<part>` as intended.

### Decimate script
Currently will take the meshes in the folder and decimate them to 50 000 faces/triangles and export them into a file. Currently, if the files are below 50,000, it just ignores them but this is unhelpful in that you end up with a folder with only some of the meshes and not all of them, so can we change it so that it exports those files as well? Also, do you think we can edit it so that it differentiates between mandibles and crania because cba splitting them manually. Also, whilst we’re at it, cna we make it so it outputs all the file names in the same format?
E.g. Genus_species_crania_dec.ply / Genus_species_mandible_dec.ply

### Throughout
- Check for redundant code/inefficencies, e.g. VTK Viewer now exports the images, no need to display the images/hold the script.
- Look into potential speed ups.
- Consider moving all current magic number/variables into an .env file, templated by an .env.example file, e.g. folder paths/imports, etc.
- Git ignore any files not required such as the contents within /meshes so people don't accidentally upload their own work/files

### Automation
Main final goal is to consider a complete automation loop of all of the above, requiring only human in the loop for manual verification of correct alignment OR if the watertight checks fail and require manual rework. Consider if we can have some sort of local yaml pipeline that will allow us to run both our python scripts and R scripts following one another whilst being correctly dependent on the previous completing successfully.

## Initial notes/rough guidance/explaination of scripts/usage
Measure volumes - this script measures the volumes and length of the inputted meshes and tells you whether they are watertight or not. 

Decimate meshes - Currently will take the meshes in the folder and decimate them to 50 000 faces/triangles and export them into a file.

ply -> ascii - Batch conversion from ply to ascii

R Script for alignment using landmarks - inputs include the ascii files and a file of the landmarks that the script uses to align the meshes. 

aligned ply -> vtk - Convert the aligned meshes to vtk and then can use the vtk viewer to check they are correctly orientated and then the meshes will be ready to go into DAA

VTK viewer - Shows all six orientations of the skull, to be used after aligning the skulls to check that they are all correctly positioned and then also post DAA with the landmarks on to check that everything looks okay. 

XML generation - Before the meshes go into the DAA, you need to create the xml file that has a list of the meshes going in, and also create the initial template file (copy and paste one of the any of the mesh vtk files). Then the files to go into the DAA are the meshes, the xml file, as well as the other two files (which I can’t remember right now, think they’re both parameter files). 

CSV/kPCA generation - .....

## License

MIT — see [LICENSE](LICENSE).