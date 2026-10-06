"""フォルダー名だけを変更したコアと拡張の実行を検証する。"""

from pathlib import Path
import ast
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


_SMOKE = r'''
import importlib
import importlib.abc
import json
import sys
import types

class RejectOriginal(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "hlib" or fullname.startswith(("hlib.", "hlib_")):
            raise AssertionError("Original package imported: " + fullname)

sys.meta_path.insert(0, RejectOriginal())
sys.path.insert(0, sys.argv[1])
# 外部SDK自体の動作ではなく、拡張の基底クラスと登録先の接続を検証する。
for name in ("epic_pose_wrangler", "epic_pose_wrangler.v2", "epic_pose_wrangler.v2.model",
             "epic_pose_wrangler.v2.model.api", "epic_pose_wrangler.v2.model.pose_blender"):
    module = types.ModuleType(name)
    module.__path__ = []
    sys.modules[name] = module
sys.modules["epic_pose_wrangler.v2.model.api"].RBFNode = type("RBFNode", (), {})
sys.modules["epic_pose_wrangler.v2.model.pose_blender"].UEPoseBlenderNode = type("UEPoseBlenderNode", (), {})

import maya.standalone
maya.standalone.initialize(name="python")
from maya import cmds
from maya.api import OpenMaya as om
try:
    for name in ("mlib", "studio_lib"):
        extension = importlib.import_module(name + "_bifrost")
        assert name not in sys.modules  # 拡張の先行importではコアを読まない。
        core = importlib.import_module(name)
        assert core.utils.logger.get_logger().name == name
        states = core.extensions.status()
        assert states[name + "_bifrost"]["state"] in ("loaded", "unavailable"), states
        assert states[name + "_posedriverconnect"]["state"] == "loaded", states
        assert states[name + "_fixture_bad"]["state"] == "error", states
        assert all(key.startswith(name + "_") for key in states), states
        binding = importlib.import_module(name + "_bifrost._binding")
        assert binding.coreModule() is core
        assert extension.nodes.Graph is not None
        assert issubclass(core.nodes.Node._registry.lookup("UERBFSolverNode"), core.nodes.Node)
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        node = core.createNode("transform")
        assert isinstance(node, core.nodes.Node)
        node.getPlug("tx").set(3)
        cmds.undo()
        assert node.getPlug("tx").get() == 0
        node.getPlug("translate").set((1, 2, 3), fast=True)
        assert tuple(node.getTranslation()) == (1, 2, 3)
        mesh = core.createPolygon(constructionHistory=False)
        mesh.vertex(0).setPosition((2, 3, 4))
        assert tuple(mesh.vertex(0).getPosition()) == (2, 3, 4)
        assert isinstance(core.Object(node.getFullName()), core.nodes.Node)
        saved = core.json.capture(node, kind="pose")
        document = core.json.JsonDocument(saved).asData()
        assert document["format"] == "hlib.json"
        assert core.json.JsonDocument.fromData(document).data.plan().errors == []
        old_node_type = core.nodes.Node
        old_extension = sys.modules[name + "_posedriverconnect"]
        core.reload()
        assert core.nodes.Node is not old_node_type
        assert sys.modules[name + "_posedriverconnect"] is not old_extension
        assert issubclass(core.nodes.Node._registry.lookup("UERBFSolverNode"), core.nodes.Node)
        assert core.extensions.status()[name + "_fixture_bad"]["state"] == "error"
        assert isinstance(core.getNode(node.getFullName()), core.nodes.Node)
    assert not any(key == "hlib" or key.startswith(("hlib.", "hlib_")) for key in sys.modules)
    print("RENAMED_PACKAGE_OK")
finally:
    maya.standalone.uninitialize()
'''


class PackageNameTest(unittest.TestCase):
    """元名へのフォールバックなしで通常編集・拡張・reloadを検証する。"""

    def test_documentation_names_and_stable_identifiers(self):
        """本文・リンクを変換し、保存形式・宣言・外部URLを保持する。"""
        root = Path(__file__).resolve().parents[1]
        tree = ast.parse((root / "docs/conf.py").read_text(encoding="utf8"))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                        and node.name == "_adapt_package_name")
        isolated = ast.parse("")
        isolated.body = [function]
        namespace = {"_PACKAGE_NAME": "studio_library", "re": re}
        exec(compile(isolated, "conf.py", "exec"), namespace)
        original = ('hlib\n====\nimport hlib\nfrom hlib_bifrost import nodes\n'
                    'autoapi/hlib/nodes/node/Node\n:class:\u0060hlib.nodes.Node\u0060\n'
                    'format="hlib.json"\nHLIB_EXTENSION_API = 1\n'
                    'https://example.org/hlib/api\nwhyhlib\n')
        source = [original]
        namespace["_adapt_package_name"](None, "index", source)
        self.assertIn("import studio_library", source[0])
        self.assertIn("from studio_library_bifrost import nodes", source[0])
        self.assertIn("autoapi/studio_library/nodes/node/Node", source[0])
        self.assertIn(":class:\u0060studio_library.nodes.Node\u0060", source[0])
        self.assertIn('format="hlib.json"', source[0])
        self.assertIn("HLIB_EXTENSION_API = 1", source[0])
        self.assertIn("https://example.org/hlib/api", source[0])
        self.assertIn("whyhlib", source[0])
        self.assertGreaterEqual(len(source[0].splitlines()[1]), len("studio_library"))
        namespace["_PACKAGE_NAME"] = "hlib"
        source = [original]
        namespace["_adapt_package_name"](None, "index", source)
        self.assertEqual(source[0], original)

    def test_no_absolute_package_imports(self):
        """通常テストが通らない遅延importにも固定名を再導入しない。"""
        root = Path(__file__).resolve().parents[1]
        roots = (root, root.parent / "hlib_bifrost",
                 root.parent / "hlib_posedriverconnect/scripts/hlib_posedriverconnect")
        for package in roots:
            for path in package.rglob("*.py"):
                if any(part in {"docs", "__tests__", "__pycache__"} for part in path.parts):
                    continue
                tree = ast.parse(path.read_text(encoding="utf8"))
                for node in ast.walk(tree):
                    names = []
                    if isinstance(node, ast.Import):
                        names = [alias.name for alias in node.names]
                    elif isinstance(node, ast.ImportFrom) and not node.level:
                        names = [node.module or ""]
                    for name in names:
                        self.assertFalse(name == "hlib" or name.startswith(("hlib.", "hlib_")),
                                         "{}:{} {}".format(path, node.lineno, name))

    def test_renamed_packages_in_fresh_maya(self):
        """単純名とアンダースコアを含む名前を、ソース置換なしで使える。"""
        if Path(sys.executable).stem.lower() != "mayapy":
            self.skipTest("独立した mayapy で実行するテスト")
        core = Path(__file__).resolve().parents[1]
        inhouse = core.parent
        ignore = shutil.ignore_patterns("__tests__", "docs", "__pycache__", "*.pyc")
        with tempfile.TemporaryDirectory(prefix="renamed_packages_") as temporary:
            root = Path(temporary)
            for name in ("mlib", "studio_lib"):
                for source, target in (
                    (core, name),
                    (inhouse / "hlib_bifrost", name + "_bifrost"),
                    (inhouse / "hlib_posedriverconnect/scripts/hlib_posedriverconnect", name + "_posedriverconnect"),
                ):
                    shutil.copytree(str(source), str(root / target), ignore=ignore)
                bad = root / (name + "_fixture_bad")
                bad.mkdir()
                (bad / "__init__.py").write_text(
                    "HLIB_EXTENSION_API = 1\ndef is_available(): return True\n", encoding="utf8")
                (bad / "invalid.py").write_text("import " + name + "_bifrost\n", encoding="utf8")
            script = root / "smoke.py"
            script.write_text(_SMOKE, encoding="utf8")
            result = subprocess.run(
                [sys.executable, str(script), temporary], stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, timeout=180,
            )
            output = result.stdout.decode("utf8", errors="replace")
            self.assertEqual(result.returncode, 0, output)
            self.assertIn("RENAMED_PACKAGE_OK", output)


if __name__ == "__main__":
    unittest.main()
