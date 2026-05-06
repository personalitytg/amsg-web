import zipfile
from pathlib import Path


def _add_file(zip_file: zipfile.ZipFile, path: Path, arcname: Path):
    if path.exists() and path.is_file():
        zip_file.write(path, arcname.as_posix())


def _add_dir(zip_file: zipfile.ZipFile, path: Path, arc_prefix: Path):
    if not path.exists():
        return
    for item in path.rglob("*"):
        if item.is_file():
            relative = item.relative_to(path)
            zip_file.write(item, (arc_prefix / relative).as_posix())


def create_bundle(run_dir: Path, project_root: Path):
    run_dir = Path(run_dir).resolve()
    project_root = Path(project_root).resolve()

    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing manifest: {manifest_path}")

    bundle_path = run_dir / "bundle.zip"
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        _add_file(zip_file, project_root / "PROJECT_CONTEXT.md", Path("PROJECT_CONTEXT.md"))
        _add_dir(zip_file, project_root / "prompts", Path("prompts"))
        _add_dir(zip_file, project_root / "configs", Path("configs"))
        _add_file(
            zip_file,
            manifest_path,
            Path("runs") / run_dir.name / "manifest.json",
        )
        _add_file(
            zip_file,
            run_dir / "top_candidates.csv",
            Path("runs") / run_dir.name / "top_candidates.csv",
        )
        _add_file(
            zip_file,
            run_dir / "events.csv",
            Path("runs") / run_dir.name / "events.csv",
        )

        for item in run_dir.iterdir():
            if item.is_file() and item.name.startswith("control_"):
                _add_file(
                    zip_file,
                    item,
                    Path("runs") / run_dir.name / item.name,
                )

        inspect_dir = run_dir / "inspect"
        if inspect_dir.exists():
            _add_dir(
                zip_file,
                inspect_dir,
                Path("runs") / run_dir.name / "inspect",
            )

        for item in run_dir.iterdir():
            if item.is_file() and item.name.startswith("inputs"):
                _add_file(
                    zip_file,
                    item,
                    Path("runs") / run_dir.name / item.name,
                )

    return bundle_path
