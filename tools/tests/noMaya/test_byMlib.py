"""tools/by_mlib.py が byMlib/ の mlib 版を元のモジュールの代わりに読み込むことを確かめる(Maya 不要)。"""

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TOOLS))

import by_mlib  # noqa: E402


class ByMlibTest(unittest.TestCase):
    """差し替えの対象・対象外・子のモジュール・子のプロセス。"""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        root = Path(self.folder.name) / "tool"
        (root / "pkg").mkdir(parents=True)
        (root / "byMlib" / "pkg").mkdir(parents=True)
        (root / "pkg" / "__init__.py").write_text("NAME = 'original'\n", encoding="utf-8")
        (root / "pkg" / "kept.py").write_text("NAME = 'original'\n", encoding="utf-8")
        (root / "pkg" / "swapped.py").write_text("NAME = 'original'\n", encoding="utf-8")
        (root / "byMlib" / "pkg" / "__init__.py").write_text("NAME = 'byMlib'\n", encoding="utf-8")
        (root / "byMlib" / "pkg" / "swapped.py").write_text("NAME = 'byMlib'\nfrom . import kept\n", encoding="utf-8")
        self.root = root
        sys.path.insert(0, str(root))
        self.saved_meta_path = list(sys.meta_path)

    def tearDown(self):
        sys.meta_path[:] = self.saved_meta_path
        sys.path.remove(str(self.root))
        for name in [name for name in sys.modules if name == "pkg" or name.startswith("pkg.")]:
            del sys.modules[name]
        self.folder.cleanup()

    def test_replaces_only_files_that_exist_in_by_mlib(self):
        finder = by_mlib.install([str(self.root)])
        import pkg
        import pkg.kept
        import pkg.swapped

        self.assertEqual(pkg.NAME, "byMlib")
        self.assertEqual(pkg.swapped.NAME, "byMlib")
        self.assertEqual(pkg.kept.NAME, "original")
        self.assertEqual(sorted(finder.replaced), ["pkg", "pkg.swapped"])

    def test_child_process_uses_the_same_replacement(self):
        script = Path(self.folder.name) / "child.py"
        script.write_text(textwrap.dedent("""
            import subprocess, sys
            out = subprocess.run([sys.executable, "-c", "import pkg.swapped; print(pkg.swapped.NAME)"], capture_output=True, text=True)
            print(out.stdout.strip())
        """), encoding="utf-8")
        environment = dict(os.environ, PYTHONPATH=str(self.root))
        result = subprocess.run([sys.executable, str(TOOLS / "by_mlib.py"), str(self.root), "--", str(script)], capture_output=True, text=True, env=environment)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "byMlib")


if __name__ == "__main__":
    unittest.main()
