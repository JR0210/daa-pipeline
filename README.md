# Setup

```
pip install -r requirements.txt
cp .env.example .env   # then edit DATA_ROOT, RSCRIPT_PATH, LANDMARKS_CSV, etc.
```

Every script now takes CLI flags instead of a hardcoded path at the top of
the file. Run any script with `--help` to see its options. Common flags
across all scripts: `--data-root`, `--part {crania,mandible,both}`,
`--input`, `--output`, `--jobs`, `--overwrite`, `--dry-run`, `-v`.

Scripts skip work whose output already exists unless you pass `--overwrite`,
so the whole sequence below is safe to re-run after fixing a problem partway
through.

# Order of Operations

```
python measure_vol.py --input 01_raw --require-watertight
python decimate.py --part both
python measure_vol.py --part both --require-watertight   # confirm decimated output is still watertight
# If not watertight, manually rework the offending mesh(es) and re-run decimate.py --overwrite
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

## New features/changes required

**Status (Stage 1, complete):** decimate now copies through sub-threshold
meshes with canonical `Genus_species_<part>_dec.ply` naming and splits
crania/mandible automatically; every script takes CLI args with settings
in `.env`/`.env.example`; `vtk_viewer.py` renders offscreen with no window
or blocking; `.gitignore` excludes `meshes/` and all pipeline output dirs;
and a set of real bugs (see `daa/`, script docstrings, and `ascii_alignment.r`
comments for specifics) that either crashed on current dependency versions
or silently produced wrong output have been fixed. Full automation
(**Stage 2**, not yet built) is feasible with three human gates —
watertightness, visual alignment QC, and the external Deformetrica run —
everything else can run unattended via a `pipeline.yaml` + runner.

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