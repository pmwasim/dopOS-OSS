import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from validate_companyos import validate

class ValidatorTests(unittest.TestCase):
    def test_baseline_passes(self):
        self.assertTrue(validate(Path(__file__).parents[1])["ok"])
    def test_missing_metadata_fails(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); (root / "docs/00-control").mkdir(parents=True)
            (root / "docs/index.md").write_text("00-control")
            (root / "docs/00-control/bad.md").write_text("# bad")
            self.assertFalse(validate(root)["ok"])

if __name__ == "__main__": unittest.main()
