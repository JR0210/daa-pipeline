"""Render six standard views (dorsal/ventral/posterior/lateral x2/anterior)
of each VTK mesh to a single PNG, for visual alignment QC.

Renders offscreen -- no window is shown and nothing blocks -- so this can
run unattended as part of the pipeline. Review the PNGs under
07_qc_images/<part>/ before approving the alignment stage.

Usage:
    python vtk_viewer.py --part both [--jobs N] [--overwrite]
"""

from __future__ import annotations

import logging
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from daa.cli import build_parser, parts_to_process, resolve_settings, setup_logging
from daa.report import write_stage_report

logger = logging.getLogger("daa")

RESULT_FIELDS = ["filename", "output_filename"]
ERROR_FIELDS = ["filename", "error"]

LABELS = ["DORSAL", "VENTRAL", "POSTERIOR", "LEFT LATERAL", "RIGHT LATERAL", "ANTERIOR"]


def render_six_views(vtk_path: Path, output_path: Path) -> None:
    import vtk

    reader = vtk.vtkPolyDataReader()
    reader.SetFileName(str(vtk_path))
    reader.Update()

    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(reader.GetOutputPort())

    actor_mesh = vtk.vtkActor()
    actor_mesh.SetMapper(mapper)
    actor_mesh.GetProperty().SetColor(0.8, 0.8, 0.8)
    actor_mesh.GetProperty().SetAmbient(0.2)
    actor_mesh.GetProperty().SetDiffuse(0.8)
    actor_mesh.GetProperty().SetSpecular(0.2)

    bounds = actor_mesh.GetBounds()
    xmin, xmax, ymin, ymax, zmin, zmax = bounds
    center_x = (xmin + xmax) / 2
    center_y = (ymin + ymax) / 2
    center_z = (zmin + zmax) / 2
    max_size = max(xmax - xmin, ymax - ymin, zmax - zmin)
    camera_distance = max_size * 2.5

    render_window = vtk.vtkRenderWindow()
    render_window.SetOffScreenRendering(1)
    render_window.SetSize(1600, 1000)

    renderers = []
    for _ in range(6):
        renderer = vtk.vtkRenderer()
        renderer.AddActor(actor_mesh)
        renderer.SetBackground(1.0, 1.0, 1.0)
        renderers.append(renderer)
        render_window.AddRenderer(renderer)

    viewports = [
        (0.00, 0.50, 0.333, 1.00),
        (0.333, 0.50, 0.666, 1.00),
        (0.666, 0.50, 1.00, 1.00),
        (0.00, 0.00, 0.333, 0.50),
        (0.333, 0.00, 0.666, 0.50),
        (0.666, 0.00, 1.00, 0.50),
    ]
    for renderer, viewport in zip(renderers, viewports):
        renderer.SetViewport(*viewport)

    # Coordinate convention: -Y=dorsal, +Y=ventral, -X=left, +X=right,
    # +Z=posterior, -Z=anterior.
    camera_positions = [
        (center_x, center_y - camera_distance, center_z),
        (center_x, center_y + camera_distance, center_z),
        (center_x, center_y, center_z + camera_distance),
        (center_x - camera_distance, center_y, center_z),
        (center_x + camera_distance, center_y, center_z),
        (center_x, center_y, center_z - camera_distance),
    ]

    for renderer, camera_position, label in zip(renderers, camera_positions, LABELS):
        camera = renderer.GetActiveCamera()
        camera.SetPosition(camera_position)
        camera.SetFocalPoint(center_x, center_y, center_z)
        camera.SetViewUp(0, 0, 1)
        renderer.ResetCamera()

        text_actor = vtk.vtkTextActor()
        text_actor.SetInput(label)
        text_actor.GetTextProperty().SetFontSize(24)
        text_actor.GetTextProperty().SetColor(0.0, 0.0, 0.0)
        text_actor.SetPosition(15, 15)
        renderer.AddActor2D(text_actor)

    render_window.Render()

    window_to_image = vtk.vtkWindowToImageFilter()
    window_to_image.SetInput(render_window)
    window_to_image.SetInputBufferTypeToRGBA()
    window_to_image.ReadFrontBufferOff()
    window_to_image.Update()

    png_writer = vtk.vtkPNGWriter()
    png_writer.SetFileName(str(output_path))
    png_writer.SetInputConnection(window_to_image.GetOutputPort())
    png_writer.Write()

    render_window.Finalize()


def render_one(job: tuple[str, str]) -> dict:
    """Worker: render a single mesh's six-view QC image. Runs in a subprocess."""
    vtk_path_str, output_path_str = job
    vtk_path = Path(vtk_path_str)
    output_path = Path(output_path_str)
    try:
        render_six_views(vtk_path, output_path)
        return {"ok": True, "filename": vtk_path.name, "output_filename": output_path.name}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "filename": vtk_path.name, "error": f"{type(e).__name__}: {e}"}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser(
        "Render six standard views of each VTK mesh to a PNG for alignment QC "
        "(offscreen, no window shown)."
    )
    args = parser.parse_args(argv)
    setup_logging(args.verbose)

    settings = resolve_settings(args)
    parts = parts_to_process(args)

    jobs: list[tuple[str, str]] = []
    skipped: list[dict] = []

    for part in parts:
        input_dir = Path(args.input) if args.input else settings.stage_dir("vtk", part)
        output_dir = Path(args.output) if args.output else settings.stage_dir("qc_images", part)

        if not input_dir.is_dir():
            logger.warning("Input folder does not exist, skipping part %s: %s", part, input_dir)
            continue

        output_dir.mkdir(parents=True, exist_ok=True)

        vtk_files = sorted(p for p in input_dir.iterdir() if p.is_file() and p.suffix.lower() == ".vtk")
        logger.info("[%s] VTK files found: %d", part, len(vtk_files))

        for vtk_path in vtk_files:
            output_path = output_dir / (vtk_path.stem + "_six_views.png")
            if output_path.exists() and not args.overwrite:
                skipped.append({"filename": vtk_path.name, "output_filename": output_path.name})
                continue
            if args.dry_run:
                print(f"  would render: {vtk_path} -> {output_path}")
                continue
            jobs.append((str(vtk_path), str(output_path)))

    if args.dry_run:
        return 0

    results: list[dict] = list(skipped)
    errors: list[dict] = []

    if jobs:
        with ProcessPoolExecutor(max_workers=max(1, settings.jobs)) as pool:
            futures = [pool.submit(render_one, job) for job in jobs]
            for future in as_completed(futures):
                outcome = future.result()
                ok = outcome.pop("ok")
                if ok:
                    results.append(outcome)
                    logger.info("Rendered: %s -> %s", outcome["filename"], outcome["output_filename"])
                else:
                    errors.append(outcome)
                    logger.error("Failed: %s: %s", outcome["filename"], outcome["error"])

    results.sort(key=lambda r: r["filename"])
    errors.sort(key=lambda r: r["filename"])

    return write_stage_report(
        settings.reports_dir(),
        "vtk_viewer",
        results,
        errors,
        RESULT_FIELDS,
        ERROR_FIELDS,
    )


if __name__ == "__main__":
    sys.exit(main())
