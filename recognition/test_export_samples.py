import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from export_samples import export_samples


class ExportSamplesTest(unittest.TestCase):
    def test_delete_waits_until_every_sample_has_been_saved(self):
        png = io.BytesIO()
        Image.new("L", (28, 28), color=255).save(png, format="PNG")
        image = png.getvalue()
        first = "00000000-0000-0000-0000-000000000001--ERASE.png"
        second = "00000000-0000-0000-0000-000000000002--unlabeled.png"
        listing = [b"no_backup\n", b"recognition-samples\n", f"{first}\n{second}\n".encode()]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            with patch("export_samples.adb", side_effect=[*listing, image, image[:-1]]) as adb:
                with self.assertRaises(ValueError):
                    export_samples("book", output, delete=True)
                self.assertEqual(adb.call_count, 5)

            with patch("export_samples.adb", side_effect=[*listing, image, image, b""]) as adb:
                self.assertEqual(export_samples("book", output, delete=True), 2)
                deleted = adb.call_args.args[0]
                self.assertEqual(deleted[-4:], [
                    "rm", "-f", f"no_backup/recognition-samples/{first}", f"no_backup/recognition-samples/{second}"
                ])

            self.assertEqual((output / "ERASE" / first.replace("--ERASE", "")).read_bytes(), image)
            self.assertEqual((output / "unlabeled" / second.replace("--unlabeled", "")).read_bytes(), image)
