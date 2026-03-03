"""Verify sdist/wheel build artifacts and packaging metadata."""

from __future__ import annotations

import shutil
import subprocess
import tarfile
import tomllib
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DIST_DIR = REPO_ROOT / "dist"
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
EXPECTED_ENTRYPOINT = "mealplan = mealplan.cli.main:main"


def _read_project_metadata() -> tuple[str, str]:
    data = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    project = data["project"]
    name = str(project["name"])
    version = str(project["version"])
    return name, version


def _build_artifacts() -> None:
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)

    subprocess.run(["uv", "build"], cwd=REPO_ROOT, check=True)


def _assert_dist_layout() -> tuple[Path, Path]:
    if not DIST_DIR.exists():
        raise AssertionError("dist/ was not created by `uv build`.")

    wheels = sorted(DIST_DIR.glob("*.whl"))
    sdists = sorted(DIST_DIR.glob("*.tar.gz"))

    if len(wheels) != 1:
        raise AssertionError(f"Expected exactly one wheel in dist/, found {len(wheels)}.")
    if len(sdists) != 1:
        raise AssertionError(f"Expected exactly one sdist in dist/, found {len(sdists)}.")

    return wheels[0], sdists[0]


def _read_member_from_wheel(wheel_path: Path, suffix: str) -> str:
    with zipfile.ZipFile(wheel_path) as archive:
        member_name = next((name for name in archive.namelist() if name.endswith(suffix)), None)
        if member_name is None:
            raise AssertionError(f"Wheel is missing required file with suffix: {suffix}")
        return archive.read(member_name).decode("utf-8")


def _verify_wheel(wheel_path: Path, expected_name: str, expected_version: str) -> None:
    metadata = _read_member_from_wheel(wheel_path, ".dist-info/METADATA")
    if f"Name: {expected_name}" not in metadata:
        raise AssertionError(f"Wheel metadata is missing package name `{expected_name}`.")
    if f"Version: {expected_version}" not in metadata:
        raise AssertionError(f"Wheel metadata is missing version `{expected_version}`.")

    entry_points = _read_member_from_wheel(wheel_path, ".dist-info/entry_points.txt")
    if "[console_scripts]" not in entry_points:
        raise AssertionError("Wheel entry_points.txt is missing [console_scripts] section.")
    if EXPECTED_ENTRYPOINT not in entry_points:
        raise AssertionError(f"Wheel entry_points.txt is missing `{EXPECTED_ENTRYPOINT}`.")


def _verify_sdist(sdist_path: Path, expected_name: str, expected_version: str) -> None:
    with tarfile.open(sdist_path, mode="r:gz") as archive:
        member_name = next(
            (name for name in archive.getnames() if name.endswith("/PKG-INFO")),
            None,
        )
        if member_name is None:
            raise AssertionError("sdist is missing PKG-INFO metadata.")

        member = archive.extractfile(member_name)
        if member is None:
            raise AssertionError("Could not read PKG-INFO from sdist.")

        metadata = member.read().decode("utf-8")

    if f"Name: {expected_name}" not in metadata:
        raise AssertionError(f"sdist PKG-INFO is missing package name `{expected_name}`.")
    if f"Version: {expected_version}" not in metadata:
        raise AssertionError(f"sdist PKG-INFO is missing version `{expected_version}`.")


def main() -> None:
    package_name, package_version = _read_project_metadata()
    _build_artifacts()
    wheel_path, sdist_path = _assert_dist_layout()
    _verify_wheel(wheel_path, expected_name=package_name, expected_version=package_version)
    _verify_sdist(sdist_path, expected_name=package_name, expected_version=package_version)

    print(f"Verified artifacts: {wheel_path.name}, {sdist_path.name}")


if __name__ == "__main__":
    main()
