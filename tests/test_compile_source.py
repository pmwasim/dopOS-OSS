import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class CompileSourceTests(unittest.TestCase):
    def run_script(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "scripts/compile_source.py", "--root", str(root)],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )

    def test_compiles_valid_source_without_bytecode(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / "good.py").write_text("value = 1\n")
            result = self.run_script(root)
            self.assertEqual(result.returncode, 0); self.assertFalse(list(root.rglob("*.pyc")))

    def test_reports_invalid_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / "bad.py").write_text("def broken(:\n")
            result = self.run_script(root)
            self.assertEqual(result.returncode, 1); self.assertIn("bad.py", result.stdout)
