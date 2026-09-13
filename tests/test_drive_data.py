from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from drive_data import (
    DriveFile,
    REQUIRED_FILES,
    folder_id_from_url,
    select_required_drive_files,
    validate_data_directory,
)


class DriveDataTests(TestCase):
    def test_folder_id_from_share_url(self):
        self.assertEqual(
            folder_id_from_url(
                "https://drive.google.com/drive/folders/abc_DEF-12345?usp=drive_link"
            ),
            "abc_DEF-12345",
        )

    def test_recursive_manifest_selection(self):
        entries = [DriveFile("legacy", "Data_CC/\\prior_analysis0.npz")]
        entries.extend(
            DriveFile(str(index), f"Web-based App/Data_CC/Prior/{filename}")
            for index, filename in enumerate(REQUIRED_FILES)
        )
        selected = select_required_drive_files(entries)
        self.assertEqual(set(selected), set(REQUIRED_FILES))
        self.assertNotEqual(selected["prior_analysis0.npz"].file_id, "legacy")

    def test_missing_files_are_reported(self):
        with TemporaryDirectory() as directory:
            problems = validate_data_directory(Path(directory), check_archives=False)
        self.assertEqual(len(problems), len(REQUIRED_FILES))
