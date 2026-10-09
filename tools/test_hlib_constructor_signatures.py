"""Maya不要で、AutoAPIの単数Node constructor署名の補完範囲を検証する。"""

from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

_DOCS_ROOT = Path(__file__).resolve().parents[1] / "maya/inhouse/hlib/_docs"
sys.path.insert(0, str(_DOCS_ROOT))

from _constructorSignatures import ConstructorDocumentation


def _class(identifier, *, args="", bases=(), constructor=None):
    """AutoAPIのクラス表示に必要な情報だけを保持する。"""
    return SimpleNamespace(
        id=identifier, args=args, bases=list(bases), constructor=constructor,
    )


def _environment(*objects):
    """完全名で基底を解決できるビルド中の環境を用意する。"""
    app = SimpleNamespace(
        env=SimpleNamespace(autoapi_all_objects={obj.id: obj for obj in objects}),
    )
    for obj in objects:
        obj.app = app
    return app


class ConstructorDocumentationTest(unittest.TestCase):
    """既存表示を保ち、Nodeの単一継承だけに基底署名を表示する。"""

    def setUp(self):
        """hlibの完全名を対象にする。"""
        self.docs = ConstructorDocumentation("hlib")
        self.node = _class(
            "hlib.nodes.node.Node", args="node, *, create=False",
            bases=["hlib._core.object.Object"],
        )

    def test_own_signature_is_preserved_without_an_environment(self):
        """独自署名はNode系統・環境の有無にかかわらずそのまま返す。"""
        for identifier, args in (
            (self.node.id, self.node.args),
            ("hlib.maths.vector.Vector", "x=0.0, y=0.0, z=0.0"),
            ("hlib.common.scene.Scene", "path"),
        ):
            with self.subTest(identifier=identifier):
                obj = _class(identifier, args=args, bases=["unknown.Base"])
                self.assertEqual(self.docs.signature(obj), args)

    def test_three_generations_use_node_signature_without_mutation(self):
        """三段の派生を完全名で辿り、全クラスの解析情報を変更しない。"""
        dag = _class("hlib.nodes.dagNode.DagNode", bases=[self.node.id])
        transform = _class("hlib.nodes.transform.Transform", bases=[dag.id])
        joint = _class("hlib.nodes.joint.Joint", bases=[transform.id])
        objects = [self.node, dag, transform, joint]
        app = _environment(*objects)
        before = [(obj.id, obj.args, tuple(obj.bases), obj.constructor, obj.app)
                  for obj in objects]
        registry_before = dict(app.env.autoapi_all_objects)
        for obj in objects:
            self.assertEqual(self.docs.signature(obj), self.node.args)
        after = [(obj.id, obj.args, tuple(obj.bases), obj.constructor, obj.app)
                 for obj in objects]
        self.assertEqual(before, after)
        self.assertEqual(registry_before, app.env.autoapi_all_objects)

    def test_nearest_constructor_wins_after_node_lineage_is_confirmed(self):
        """最近接の独自署名を採用してもNodeまでの系統検査を続ける。"""
        parent = _class("hlib.nodes.custom.Custom", args="value, *, create=False",
                        bases=[self.node.id])
        child = _class("hlib.nodes.child.Child", bases=[parent.id])
        _environment(self.node, parent, child)
        self.assertEqual(self.docs.signature(child), parent.args)

    def test_skin_cluster_keeps_its_own_arguments(self):
        """SkinClusterの引数名をNodeの引数名へ置き換えない。"""
        skin = _class("hlib.nodes.skinCluster.SkinCluster",
                      args="skin_cluster, *, create=False", bases=[self.node.id])
        child = _class("hlib.nodes.skinChild.SkinChild", bases=[skin.id])
        _environment(self.node, skin, child)
        self.assertEqual(self.docs.signature(skin), skin.args)
        self.assertEqual(self.docs.signature(child), skin.args)

    def test_other_lineages_keep_an_empty_signature(self):
        """数学型やcommonの基底に署名があってもNodeの派生でなければ使わない。"""
        for identifier in ("hlib.maths.vector.Vector", "hlib.common.scene.Scene"):
            with self.subTest(identifier=identifier):
                parent = _class(identifier, args="value", bases=["builtins.object"])
                child = _class(identifier + "Child", bases=[parent.id])
                _environment(self.node, parent, child)
                self.assertEqual(self.docs.signature(child), "")

    def test_unknown_bases_and_missing_environment_keep_an_empty_signature(self):
        """未知の基底やビルド環境のない表示には署名を推測しない。"""
        child = _class("hlib.nodes.child.Child", args=None,
                       bases=["hlib.nodes.missing.Missing"])
        self.assertEqual(self.docs.signature(child), "")
        _environment(self.node, child)
        self.assertEqual(self.docs.signature(child), "")
        parent = _class("hlib.nodes.parent.Parent", args="special",
                        bases=["hlib.nodes.missing.Missing"])
        child.bases = [parent.id]
        _environment(self.node, parent, child)
        self.assertEqual(self.docs.signature(child), "")

    def test_cycles_do_not_use_an_intermediate_signature(self):
        """途中で署名が見つかっても循環した基底からは採用しない。"""
        first = _class("hlib.nodes.first.First", bases=["hlib.nodes.second.Second"])
        second = _class("hlib.nodes.second.Second", args="special", bases=[first.id])
        _environment(self.node, first, second)
        self.assertEqual(self.docs.signature(first), "")

    def test_multiple_bases_at_any_level_keep_an_empty_signature(self):
        """自身と途中の基底のどちらでも多重継承なら補完しない。"""
        for direct in (False, True):
            with self.subTest(direct=direct):
                parent = _class("hlib.nodes.parent.Parent", args="special",
                                bases=[self.node.id, "hlib.common.mixin.Mixin"])
                child = _class("hlib.nodes.child.Child",
                               bases=list(parent.bases) if direct else [parent.id])
                _environment(self.node, parent, child)
                self.assertEqual(self.docs.signature(child), "")

    def test_renamed_package_has_its_own_node_boundary(self):
        """mlibへ改名しても同じ規則で解決し、別パッケージのNodeを混ぜない。"""
        node = _class("mlib.nodes.node.Node", args="node, *, create=False")
        dag = _class("mlib.nodes.dagNode.DagNode", bases=[node.id])
        transform = _class("mlib.nodes.transform.Transform", bases=[dag.id])
        child = _class("mlib.nodes.joint.Joint", bases=[transform.id])
        _environment(node, dag, transform, child)
        self.assertEqual(ConstructorDocumentation("mlib").signature(child), node.args)
        self.assertEqual(self.docs.signature(child), "")

    def test_empty_own_constructor_is_not_replaced_with_node_arguments(self):
        """明示された引数なしconstructorへ基底の引数を付け足さない。"""
        parent = _class("hlib.nodes.parent.Parent", bases=[self.node.id],
                        constructor=SimpleNamespace(inherited=False))
        child = _class("hlib.nodes.child.Child", bases=[parent.id])
        _environment(self.node, parent, child)
        self.assertEqual(self.docs.signature(parent), "")
        self.assertEqual(self.docs.signature(child), "")

    def test_inherited_empty_constructor_does_not_hide_the_base_signature(self):
        """継承メンバーとして現れたconstructorは独自定義と判定しない。"""
        child = _class("hlib.nodes.child.Child", bases=[self.node.id],
                       constructor=SimpleNamespace(inherited=True))
        _environment(self.node, child)
        self.assertEqual(self.docs.signature(child), self.node.args)

    def test_conditional_imported_bases_agree_without_evaluating_the_condition(self):
        """条件のMaya呼出しを実行せず、import別名・モジュール属性を解決する。"""
        with TemporaryDirectory() as directory:
            root = Path(directory) / "hlib"
            (root / "nodes").mkdir(parents=True)
            (root / "nodes/lambert.py").write_text(
                "from .paintable import Paintable as PaintableAlias\n"
                "from . import shading as shading_module\n"
                "_SurfaceBase = (PaintableAlias if __import__('maya').cmds.nodeType('lambert') "
                "else shading_module.Shading)\n"
                "class Lambert(_SurfaceBase):\n    pass\n", encoding="utf-8")
            docs = ConstructorDocumentation("hlib", root)
            shading = _class("hlib.nodes.shading.Shading", bases=[self.node.id])
            paintable = _class("hlib.nodes.paintable.Paintable", bases=[shading.id])
            lambert = _class("hlib.nodes.lambert.Lambert", bases=["_SurfaceBase"])
            child = _class("hlib.nodes.blinn.Blinn", bases=[lambert.id])
            _environment(self.node, shading, paintable, lambert, child)
            self.assertEqual(docs.conditional_bases["hlib.nodes.lambert._SurfaceBase"],
                             (paintable.id, shading.id))
            self.assertEqual(docs.signature(lambert), self.node.args)
            self.assertEqual(docs.signature(child), self.node.args)
            self.assertEqual(self.docs.signature(lambert), "")

    def test_conditional_bases_reject_unknown_non_node_different_and_unsafe_lineages(self):
        """条件の片枝が不明・非Node・別署名・循環・多重なら署名を補完しない。"""
        with TemporaryDirectory() as directory:
            root = Path(directory) / "hlib"
            (root / "nodes").mkdir(parents=True)
            (root / "nodes/lambert.py").write_text(
                "from .left import Left\nfrom .right import Right\n"
                "_SurfaceBase = Left if version_is_new() else Right\n"
                "class Lambert(_SurfaceBase):\n    pass\n", encoding="utf-8")
            docs = ConstructorDocumentation("hlib", root)
            for case in ("unknown", "other", "different", "cycle", "multiple"):
                with self.subTest(case=case):
                    left = _class("hlib.nodes.left.Left", bases=[self.node.id])
                    right = _class("hlib.nodes.right.Right", bases=[self.node.id])
                    lambert = _class("hlib.nodes.lambert.Lambert", bases=["_SurfaceBase"])
                    if case == "other":
                        right.bases = ["builtins.object"]
                    elif case == "different":
                        right.args = "special, *, create=False"
                    elif case == "cycle":
                        right.bases = [lambert.id]
                    elif case == "multiple":
                        right.bases = [self.node.id, left.id]
                    objects = [self.node, left, lambert]
                    if case != "unknown":
                        objects.append(right)
                    _environment(*objects)
                    self.assertEqual(docs.signature(lambert), "")

    def test_conditional_alias_cycles_and_callable_branches_are_not_guessed(self):
        """条件付き別名の循環と、関数呼出しで決まる基底を安全に除外する。"""
        with TemporaryDirectory() as directory:
            root = Path(directory) / "hlib"
            (root / "nodes").mkdir(parents=True)
            path = root / "nodes/lambert.py"
            for source in (
                "from .node import Node\n"
                "_SurfaceBase = _OtherBase if flag else Node\n"
                "_OtherBase = _SurfaceBase if flag else Node\n",
                "from .node import Node\n"
                "_SurfaceBase = make_base() if flag else Node\n",
            ):
                with self.subTest(source=source):
                    path.write_text(source, encoding="utf-8")
                    docs = ConstructorDocumentation("hlib", root)
                    lambert = _class("hlib.nodes.lambert.Lambert", bases=["_SurfaceBase"])
                    _environment(self.node, lambert)
                    self.assertEqual(docs.signature(lambert), "")

    def test_conditional_bases_work_for_renamed_package_and_qualified_base(self):
        """改名したパッケージでも相対import・完全名の条件付き基底を使う。"""
        with TemporaryDirectory() as directory:
            root = Path(directory) / "mlib"
            (root / "nodes").mkdir(parents=True)
            (root / "nodes/surface.py").write_text(
                "import mlib.nodes.left as left_module\n"
                "from .right import Right\n"
                "_SurfaceBase = left_module.Left if flag else Right\n", encoding="utf-8")
            docs = ConstructorDocumentation("mlib", root)
            node = _class("mlib.nodes.node.Node", args="node, *, create=False")
            left = _class("mlib.nodes.left.Left", bases=[node.id])
            right = _class("mlib.nodes.right.Right", bases=[node.id])
            surface = _class("mlib.nodes.surface.Surface",
                             bases=["mlib.nodes.surface._SurfaceBase"])
            _environment(node, left, right, surface)
            self.assertEqual(docs.signature(surface), node.args)

    def test_product_surface_bases_are_collected_without_importing_hlib(self):
        """実際の二つのSurfaceBase定義を製品importなしで検出する。"""
        docs = ConstructorDocumentation("hlib", _DOCS_ROOT.parent)
        expected = (
            "hlib.nodes.paintableShadingDependNode.PaintableShadingDependNode",
            "hlib.nodes.shadingDependNode.ShadingDependNode",
        )
        for module in ("lambert", "standardSurface"):
            self.assertEqual(docs.conditional_bases[
                "hlib.nodes." + module + "._SurfaceBase"], expected)


if __name__ == "__main__":
    unittest.main()
