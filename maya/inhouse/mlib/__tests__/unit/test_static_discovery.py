"""本体テストの探索範囲と、指定ミスで空の成功を返さないことを検証する。"""
from pathlib import Path
import unittest

import run_all_tests


class DiscoveryTest(unittest.TestCase):
    def test_unit_and_integration_can_run_separately(self):
        files = run_all_tests.discover_test_files(suite="unit")
        self.assertTrue(files)
        root = Path(run_all_tests.__file__).parent / "unit"
        self.assertTrue(all(root in path.parents for path in files))
        self.assertEqual(files, sorted(files, key=lambda path: (path.name, str(path))))
        integration = run_all_tests.discover_test_files(suite="integration")
        self.assertTrue(integration)
        self.assertFalse(set(files) & set(integration))
        self.assertEqual(set(files + integration), set(run_all_tests.discover_test_files()))
        self.assertTrue(all(not path.name.startswith("test_static_") for path in files))

    def test_selects_known_file_and_rejects_a_typo(self):
        files = run_all_tests.discover_test_files(names=["test_datatypes.py"])
        self.assertEqual([path.name for path in files], ["test_datatypes.py"])
        with self.assertRaises(ValueError):
            run_all_tests.discover_test_files(names=["test_does_not_exist.py"])


if __name__ == "__main__":
    unittest.main()
