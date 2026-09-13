"""Google Drive and direct-upload data preparation for the Journal 2 model."""

from __future__ import annotations

import hashlib
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable

import numpy as np


DEFAULT_DRIVE_FOLDER_URL = (
    "https://drive.google.com/drive/folders/"
    "1Y_yZDyOBnGlCrx5KVRRidEH_Hy8Hufcg?usp=drive_link"
)


def required_filenames() -> tuple[str, ...]:
    names: list[str] = []
    for crack_id in range(3):
        names.extend(
            [
                f"prior_analysis{crack_id}.npz",
                f"Samples_HPC{crack_id}_.npz",
                f"name_Pfx_burst_leak{crack_id}.npz",
                f"name_Pfx3_burst_leak{crack_id}.npz",
                f"name_Pfy3_burst_leak{crack_id}_e1.npz",
            ]
        )
    return tuple(names)


REQUIRED_FILES = required_filenames()
EXPECTED_KEYS = {
    "prior_analysis": {"Pf_T_leak", "Pf2_T_burst"},
    "Samples_HPC": {"OriginSamples0"},
    "name_Pfx_burst": {"Pfx_burst_read"},
    "name_Pfx3": {"Pfx3_leak_read", "Pfx3_burst_read"},
    "name_Pfy3": {"Pfy3_leak_read", "Pfy3_burst_read"},
}


@dataclass(frozen=True)
class DriveFile:
    file_id: str
    path: str

    @property
    def name(self) -> str:
        # Drive contains one legacy file literally named ``\prior_analysis0.npz``.
        # A backslash is a valid Drive/Linux filename character, so preserve it
        # and match only the correctly named file in the nested Prior folder.
        return PurePosixPath(self.path).name


def folder_id_from_url(url: str) -> str:
    """Return a Drive folder id from either a share URL or a bare id."""

    value = url.strip()
    match = re.search(r"/folders/([A-Za-z0-9_-]+)", value)
    if match:
        return match.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{10,}", value):
        return value
    raise ValueError("Enter a valid Google Drive folder share link or folder ID.")


def list_public_drive_folder(folder_url: str) -> list[DriveFile]:
    """List a public Drive folder recursively without downloading its contents."""

    import gdown

    folder_id_from_url(folder_url)
    entries = gdown.download_folder(
        url=folder_url,
        quiet=True,
        use_cookies=False,
        remaining_ok=True,
        skip_download=True,
    )
    if entries is None:
        raise RuntimeError(
            "Google Drive did not return a file list. Confirm that anyone with the link can view the folder."
        )
    return [DriveFile(str(entry.id), str(entry.path)) for entry in entries]


def select_required_drive_files(entries: Iterable[DriveFile]) -> dict[str, DriveFile]:
    """Match the required model filenames in a recursive Drive listing."""

    selected: dict[str, DriveFile] = {}
    required = set(REQUIRED_FILES)
    for entry in entries:
        if entry.name in required and entry.name not in selected:
            selected[entry.name] = entry
    missing = [name for name in REQUIRED_FILES if name not in selected]
    if missing:
        raise FileNotFoundError(
            "The Drive folder is missing required files: " + ", ".join(missing)
        )
    return selected


def cache_directory(folder_url: str) -> Path:
    digest = hashlib.sha256(folder_url.strip().encode("utf-8")).hexdigest()[:14]
    return Path(tempfile.gettempdir()) / "pipeline_integrity_platform" / digest / "Data_CC"


def _expected_keys(filename: str) -> set[str]:
    for prefix, keys in EXPECTED_KEYS.items():
        if filename.startswith(prefix):
            return keys
    return set()


def validate_data_directory(data_dir: Path, check_archives: bool = True) -> list[str]:
    """Return user-facing validation problems for a staged Data_CC directory."""

    problems: list[str] = []
    for filename in REQUIRED_FILES:
        path = data_dir / filename
        if not path.is_file():
            problems.append(f"Missing {filename}")
            continue
        if not check_archives:
            continue
        try:
            with np.load(path, allow_pickle=False) as archive:
                missing_keys = _expected_keys(filename).difference(archive.files)
            if missing_keys:
                problems.append(
                    f"{filename} is missing array(s): {', '.join(sorted(missing_keys))}"
                )
        except Exception as exc:
            problems.append(f"{filename} is not a readable NPZ file: {exc}")
    return problems


def download_required_drive_data(
    folder_url: str,
    progress: Callable[[int, int, str], None] | None = None,
) -> Path:
    """Download only the 15 files required by the current Journal 2 interface."""

    import gdown

    entries = list_public_drive_folder(folder_url)
    selected = select_required_drive_files(entries)
    data_dir = cache_directory(folder_url)
    data_dir.mkdir(parents=True, exist_ok=True)
    total = len(REQUIRED_FILES)

    for index, filename in enumerate(REQUIRED_FILES, start=1):
        target = data_dir / filename
        if target.is_file():
            if progress:
                progress(index, total, filename)
            continue
        temporary = target.with_suffix(target.suffix + ".part")
        result = gdown.download(
            id=selected[filename].file_id,
            output=str(temporary),
            quiet=True,
            use_cookies=False,
            resume=True,
        )
        if not result or not temporary.is_file():
            raise RuntimeError(f"Google Drive download failed for {filename}")
        temporary.replace(target)
        if progress:
            progress(index, total, filename)

    problems = validate_data_directory(data_dir)
    if problems:
        raise ValueError("Downloaded data did not pass validation: " + "; ".join(problems))
    return data_dir


def stage_uploaded_files(uploaded_files: Iterable[object]) -> Path:
    """Stage user-uploaded NPZ files in a private temporary directory."""

    data_dir = Path(tempfile.mkdtemp(prefix="journal2_upload_")) / "Data_CC"
    data_dir.mkdir(parents=True)
    allowed = set(REQUIRED_FILES)
    for uploaded in uploaded_files:
        filename = Path(str(uploaded.name)).name
        if filename not in allowed:
            continue
        (data_dir / filename).write_bytes(uploaded.getbuffer())

    problems = validate_data_directory(data_dir)
    if problems:
        raise ValueError("Uploaded data did not pass validation: " + "; ".join(problems))
    return data_dir
