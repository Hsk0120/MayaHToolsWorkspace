"""Qt5の配布差によるビルド設定の回帰を検証する。"""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from maya_devkit import _patch_qt5_cmake


class Qt5CmakeTest(unittest.TestCase):
    """Release参照を保持し、欠落するDebug参照だけを無効にする。"""

    def test_debug_argument_positions_and_idempotence(self):
        """新旧Qt5構成を補正し、二重適用で差分が出ないことを確認する。"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'Qt5CoreConfig.cmake'
            path.write_text('\n_populate_Core_target_properties(DEBUG "Qt5Cored.dll" "Qt5Cored.lib" TRUE)\n'
                            '_populate_Core_target_properties(Qt5::Core DEBUG "Qt5Cored.dll")\n'
                            '_populate_Core_target_properties(RELEASE "Qt5Core.dll" "Qt5Core.lib" TRUE)\n', encoding='utf-8')
            _patch_qt5_cmake(directory)
            text = path.read_text(encoding='utf-8')
            self.assertEqual(sum(line.startswith('# _populate') for line in text.splitlines()), 2)
            self.assertIn('\n_populate_Core_target_properties(RELEASE', text)
            _patch_qt5_cmake(directory)
            self.assertEqual(path.read_text(encoding='utf-8'), text)


if __name__ == '__main__':
    unittest.main()
