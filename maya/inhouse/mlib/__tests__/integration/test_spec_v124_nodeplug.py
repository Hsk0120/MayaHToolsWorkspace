"""12.4.0 で足した Node・Plug・MultiPlug・Namespace・Reference のメソッドと units の変換関数を確かめる。

- Node.getSets(listSets と一致・type の絞込み)・isDefaultNode・getReference。
- Plug.getSiblings/getAllParents・isConnectable/isUsedAsColor/isWorldSpace・isDefaultValue・isFromReferencedFile・
  getAffected/getAffecting(cmds.affects と突き合わせ)・getLayeredPlug(animLayer の layeredPlug と突き合わせ)・
  insertInput(Undo 1回)、MultiPlug.getConnectedIndices。
- Namespace.getChildren(recurse)・getShortName・split・getNode・remove(deleteContents=True, Undo 1回)。
- units.convertTime・convertAngle。
- Reference.getCopyNumber・isUsingNamespaces・isDeferred・removeEdits・replaceFile・importContents。
"""

import math
import os
import shutil
import sys
import tempfile
import unittest
import uuid

import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.common import Namespace, units
from mlib.nodes.reference import Reference
from support.specCase import NamespaceCase


class _Case(NamespaceCase):
    """名前空間の補助。"""

    PREFIX = "mlibV124np_"


class NodeTest(_Case):
    """Node.getSets・isDefaultNode・getReference。"""

    def test_get_sets_matches_list_sets(self):
        """transform・shape(コンポーネントのメンバー)・DGノードのセットが listSets と一致し、type で絞れる。"""
        cube = cmds.polyCube(name=self.name("cube#"), constructionHistory=False)[0]
        shape = cmds.listRelatives(cube, shapes=True, fullPath=True)[0]
        whole = cmds.sets(cube, name=self.name("whole#"))
        faces = cmds.sets(cube + ".f[0]", name=self.name("faces#"))
        md = self.make("multiplyDivide", "md#")
        dg_set = cmds.sets(md, name=self.name("dg#"))
        for name in (cube, shape, md):
            with self.subTest(name=name):
                expected = sorted(cmds.ls(cmds.listSets(object=name) or [], long=True))
                self.assertEqual(sorted(node.getFullName() for node in mlib.getNode(name).getSets()), expected)
        self.assertEqual([node.getFullName() for node in mlib.getNode(cube).getSets()], [whole])
        shape_sets = mlib.getNode(shape).getSets()
        self.assertIn(faces, [node.getFullName() for node in shape_sets])
        self.assertEqual([node.getFullName() for node in mlib.getNode(shape).getSets(type="shadingEngine")],
                         ["initialShadingGroup"])
        self.assertIsInstance(mlib.getNode(md).getSets()[0], mlib.ObjectSet)
        self.assertEqual(mlib.getNode(md).getSets()[0].getFullName(), dg_set)
        self.assertEqual(mlib.getNode(self.make("transform")).getSets(), [])
        for value, error in ((1, TypeError), ("", ValueError)):
            with self.subTest(type=value):
                with self.assertRaises(error):
                    mlib.getNode(md).getSets(type=value)

    def test_is_default_node(self):
        """time1・lambert1 は既定ノード、作ったノードは既定ノードでない(ls(defaultNodes=True) と一致)。"""
        defaults = set(cmds.ls(defaultNodes=True))
        for name in ("time1", "lambert1", self.make("transform")):
            with self.subTest(name=name):
                self.assertEqual(mlib.getNode(name).isDefaultNode(), name in defaults)
        self.assertTrue(mlib.getNode("time1").isDefaultNode())

    def test_deleted_node_raises(self):
        """削除済みのノードは RuntimeError。"""
        node = mlib.getNode(self.make("transform"))
        cmds.delete(node.getFullName())
        for call in (node.getSets, node.isDefaultNode, node.getReference):
            with self.subTest(call=call.__name__):
                with self.assertRaises(RuntimeError):
                    call()


class PlugStructureTest(_Case):
    """Plug の構造・定義フラグ・既定値・依存関係。"""

    def test_siblings_and_all_parents(self):
        """コンパウンドアトリビュートの兄弟と、マルチアトリビュートの要素を経由した祖先。"""
        node = mlib.getNode(self.make("transform"))
        self.assertEqual([plug.getShortName() for plug in node.tx.getSiblings()], ["ty", "tz"])
        self.assertEqual(node.translate.getSiblings(), [])
        self.assertEqual([plug.getShortName() for plug in node.tx.getAllParents()], ["t"])
        pma = mlib.getNode(self.make("plusMinusAverage", "pma#"))
        child = pma.getPlug("input3D[2].input3Dx")
        self.assertEqual([plug.getName() for plug in child.getAllParents()], [pma.getName() + ".i3[2]"])
        self.assertEqual([plug.getName() for plug in child.getAllParents(includeMulti=True)],
                         [pma.getName() + ".i3[2]", pma.getName() + ".i3"])
        self.assertEqual(pma.getPlug("input1D[0]").getAllParents(), [])
        self.assertEqual([plug.getName() for plug in pma.getPlug("input1D[0]").getAllParents(includeMulti=True)],
                         [pma.getName() + ".i1"])
        with self.assertRaises(TypeError):
            child.getAllParents(includeMulti=1)

    def test_definition_flags(self):
        """connectable・usedAsColor・worldSpace の定義フラグが attributeQuery と一致する。"""
        name = self.make("transform")
        node = mlib.getNode(name)
        for attribute in ("translateX", "worldMatrix", "overrideColorRGB", "message"):
            with self.subTest(attribute=attribute):
                plug = node.getPlug(attribute)
                self.assertEqual(plug.isUsedAsColor(), cmds.attributeQuery(attribute, node=name, usedAsColor=True))
                self.assertIs(plug.isConnectable(), True)
        self.assertTrue(node.worldMatrix.isWorldSpace())
        self.assertFalse(node.tx.isWorldSpace())
        self.assertTrue(node.getPlug("overrideColorRGB").isUsedAsColor())

    def test_is_default_value(self):
        """既定値なら True、変えると False。コンパウンドアトリビュートは子がすべて既定値なら True。"""
        node = mlib.getNode(self.make("transform"))
        self.assertTrue(node.tx.isDefaultValue())
        self.assertTrue(node.translate.isDefaultValue())
        node.ty.set(2.0)
        self.assertFalse(node.ty.isDefaultValue())
        self.assertFalse(node.translate.isDefaultValue())
        self.assertTrue(node.tx.isDefaultValue())

    def test_affected_and_affecting_match_cmds(self):
        """getAffected/getAffecting のロング名が cmds.affects(by=True)/cmds.affects と一致する。"""
        name = self.make("transform")
        node = mlib.getNode(name)
        for attribute in ("translateX", "rotate", "visibility"):
            with self.subTest(attribute=attribute):
                plug = node.getPlug(attribute)
                self.assertEqual(sorted(p.getLongName() for p in plug.getAffected()),
                                 sorted(set(cmds.affects(attribute, name, by=True) or [])))
                self.assertEqual(sorted(p.getLongName() for p in plug.getAffecting()),
                                 sorted(set(cmds.affects(attribute, name) or [])))
        self.assertIn("matrix", [p.getLongName() for p in node.tx.getAffected()])

    def test_affected_multi_child_is_folded(self):
        """マルチアトリビュートの中の子は、そのマルチアトリビュート全体の Plug にまとめる。"""
        pma = mlib.getNode(self.make("plusMinusAverage", "pma#"))
        names = [p.getLongName() for p in pma.getPlug("operation").getAffected()]
        self.assertIn("output3D", names)
        affecting = [p.getLongName() for p in pma.getPlug("output3Dx").getAffecting()]
        self.assertIn("input3D", affecting)
        self.assertNotIn("input3Dx", affecting)

    def test_connected_indices(self):
        """接続のある要素(子の接続・出力接続を含む)の番号だけを返す。値だけの要素は含まない。"""
        a = mlib.getNode(self.make("transform"))
        pma = mlib.getNode(self.make("plusMinusAverage", "pma#"))
        cmds.connectAttr(a.getFullName() + ".tx", pma.getFullName() + ".input1D[3]")
        cmds.connectAttr(a.getFullName() + ".ty", pma.getFullName() + ".input1D[1]")
        cmds.setAttr(pma.getFullName() + ".input1D[7]", 2.0)
        cmds.connectAttr(a.getFullName() + ".tz", pma.getFullName() + ".input3D[5].input3Dy")
        self.assertEqual(pma.getPlug("input1D").getConnectedIndices(), [1, 3])
        self.assertEqual(pma.getPlug("input1D").getIndices(), [1, 3, 7])
        self.assertEqual(pma.getPlug("input3D").getConnectedIndices(), [5])
        self.assertEqual(pma.getPlug("input2D").getConnectedIndices(), [])
        b = mlib.getNode(self.make("transform"))
        cmds.connectAttr(a.getFullName() + ".worldMatrix[0]", b.getFullName() + ".offsetParentMatrix")
        self.assertEqual(a.getPlug("worldMatrix").getConnectedIndices(), [0])

    def test_deleted_plug_raises(self):
        """削除済みのノードの Plug は RuntimeError。"""
        node = mlib.getNode(self.make("transform"))
        plug, multi = node.tx, node.worldMatrix
        cmds.delete(node.getFullName())
        for call in (plug.getSiblings, plug.getAllParents, plug.isConnectable, plug.isUsedAsColor,
                     plug.isWorldSpace, plug.isDefaultValue, plug.isFromReferencedFile, plug.getAffected,
                     plug.getAffecting, plug.getLayeredPlug, multi.getConnectedIndices):
            with self.subTest(call=call.__name__):
                with self.assertRaises(RuntimeError):
                    call()


class InsertInputTest(_Case):
    """Plug.insertInput。"""

    def test_insert_between_connection(self):
        """入力元 → node.input1、node.output → 自身になり、Undo 1回で元の接続に戻る。"""
        a, b = self.make("transform", "a#"), self.make("transform", "b#")
        mdl = self.make("multDoubleLinear", "mdl#")
        cmds.connectAttr(a + ".tx", b + ".ty")
        plug = mlib.getPlug(b + ".ty")
        self.flushUndo()
        self.assertIs(plug.insertInput(mdl, "input1", "output"), plug)

        def after():
            self.assertEqual(cmds.listConnections(b + ".ty", source=True, destination=False, plugs=True),
                             [cmds.ls(mdl)[0] + ".output"])
            self.assertEqual(cmds.listConnections(mdl + ".input1", source=True, destination=False, plugs=True),
                             [cmds.ls(a)[0] + ".translateX"])

        def before():
            self.assertEqual(cmds.listConnections(b + ".ty", source=True, destination=False, plugs=True),
                             [cmds.ls(a)[0] + ".translateX"])
            self.assertFalse(cmds.listConnections(mdl + ".input1", source=True, destination=False))
        self.assertUndoesInOneStep(before, after)

    def test_insert_skips_conversion_and_without_input(self):
        """unitConversion を飛ばした入力元をつなぐ。入力接続が無ければ出力だけをつなぐ。"""
        a, b = self.make("transform", "a#"), self.make("transform", "b#")
        mdl = self.make("multDoubleLinear", "mdl#")
        cmds.connectAttr(a + ".rx", b + ".ty")
        mlib.getPlug(b + ".ty").insertInput(mdl, "input1", "output")
        self.assertEqual(mlib.getPlug(mdl + ".input1").getSource(skipConversionNodes=True).getFullName(),
                         mlib.getPlug(a + ".rx").getFullName())
        self.assertEqual(mlib.getPlug(b + ".ty").getSource().getFullName(), mlib.getPlug(mdl + ".output").getFullName())
        c = self.make("transform", "c#")
        mdl2 = self.make("multDoubleLinear", "mdl#")
        mlib.getPlug(c + ".tz").insertInput(mdl2, "input1", "output")
        self.assertEqual(mlib.getPlug(c + ".tz").getSource().getFullName(), mlib.getPlug(mdl2 + ".output").getFullName())
        self.assertIsNone(mlib.getPlug(mdl2 + ".input1").getSource())

    def test_insert_errors(self):
        """引数の型・空文字列・存在しないアトリビュート・入力側の既存接続は例外で、接続は変わらない。"""
        a, b = self.make("transform", "a#"), self.make("transform", "b#")
        mdl = self.make("multDoubleLinear", "mdl#")
        cmds.connectAttr(a + ".tx", b + ".ty")
        cmds.connectAttr(a + ".tz", mdl + ".input1")
        plug = mlib.getPlug(b + ".ty")
        for args, error in (((mdl, 1, "output"), TypeError), ((mdl, "input1", ""), ValueError),
                            ((mdl, "nope", "output"), RuntimeError), ((mdl, "input1", "output"), RuntimeError),
                            ((5, "input1", "output"), TypeError)):
            with self.subTest(args=args):
                with self.assertRaises(error):
                    plug.insertInput(*args)
                self.assertEqual(cmds.listConnections(b + ".ty", source=True, destination=False, plugs=True),
                                 [cmds.ls(a)[0] + ".translateX"])


class LayeredPlugTest(_Case):
    """Plug.getLayeredPlug。"""

    def setUp(self):
        super().setUp()
        self.layers = []

    def tearDown(self):
        for layer in self.layers:
            if cmds.objExists(layer):
                cmds.delete(layer)
        super().tearDown()

    def test_layered_plug_matches_anim_layer(self):
        """レイヤー指定は animLayer(layeredPlug) と一致し、既定は最上位、ベースはブレンドの連鎖の最も手前。"""
        node = self.make("transform", "a#")
        cmds.setKeyframe(node + ".tx", time=1, value=0.0)
        plug = mlib.getPlug(node + ".tx")
        self.assertIs(plug.getLayeredPlug(), plug)
        layer1 = cmds.animLayer("mlibV124Layer1_" + uuid.uuid4().hex[:6])
        layer2 = cmds.animLayer("mlibV124Layer2_" + uuid.uuid4().hex[:6])
        self.layers += [layer1, layer2]
        root = cmds.animLayer(query=True, root=True)
        if root not in self.layers:
            self.layers.append(root)
        cmds.animLayer(layer1, edit=True, attribute=node + ".tx")
        cmds.animLayer(layer2, edit=True, attribute=node + ".tx")
        for layer in (layer1, layer2):
            with self.subTest(layer=layer):
                expected = cmds.animLayer(layer, query=True, layeredPlug=node + ".tx")
                self.assertEqual(plug.getLayeredPlug(layer).getFullName(), mlib.getPlug(expected).getFullName())
        top = plug.getAnimLayers()[0]
        self.assertEqual(plug.getLayeredPlug().getFullName(),
                         mlib.getPlug(cmds.animLayer(top, query=True, layeredPlug=node + ".tx")).getFullName())
        base = plug.getLayeredPlug(root)
        curve = plug.getAnimCurve(layer=root)
        self.assertEqual(base.getSource().getNode().getFullName(), curve.getFullName())
        other = self.make("transform", "b#")
        self.assertIsNone(mlib.getPlug(other + ".tx").getLayeredPlug(layer1))
        for layer, error in ((5, TypeError), (other, TypeError), (self.name("missingLayer"), RuntimeError)):
            with self.subTest(layer=layer):
                with self.assertRaises(error):
                    plug.getLayeredPlug(layer)


class NamespaceTest(_Case):
    """Namespace の追加メソッド。"""

    def _tree(self):
        """:<ns>:a:b と :<ns>:c を作り、:<ns> の Namespace を返す。"""
        cmds.namespace(add="a", parent=":" + self.ns)
        cmds.namespace(add="b", parent=":" + self.ns + ":a")
        cmds.namespace(add="c", parent=":" + self.ns)
        return Namespace(self.ns)

    def test_children_recurse(self):
        """recurse=False は直下、True は子孫(namespaceInfo の recurse と同じ集合)。"""
        root = self._tree()
        self.assertEqual(sorted(child.name for child in root.getChildren()),
                         [":" + self.ns + ":a", ":" + self.ns + ":c"])
        expected = cmds.namespaceInfo(":" + self.ns, listOnlyNamespaces=True, recurse=True, absoluteName=True)
        self.assertEqual(sorted(child.name for child in root.getChildren(recurse=True)), sorted(expected))
        self.assertEqual(Namespace(":" + self.ns + ":missing").getChildren(recurse=True), [])
        with self.assertRaises(TypeError):
            root.getChildren(recurse=1)

    def test_short_name_and_split(self):
        """末端名・階層の分割。ルートは ':' と空リスト。"""
        namespace = Namespace(":" + self.ns + ":a:b")
        self.assertEqual(namespace.getShortName(), "b")
        self.assertEqual(namespace.split(), [self.ns, "a", "b"])
        self.assertEqual(Namespace(":").getShortName(), ":")
        self.assertEqual(Namespace(":").split(), [])

    def test_get_node(self):
        """名前空間を付けたノードを返し、無ければ RuntimeError。引数の型・空文字列は例外。"""
        name = self.make("transform", "target")
        node = Namespace(self.ns).getNode("target")
        self.assertEqual(node.getFullName(), cmds.ls(name, long=True)[0])
        self.assertEqual(Namespace(":").getNode("time1").getFullName(), "time1")
        for value, error in (("missing", RuntimeError), (1, TypeError), ("", ValueError)):
            with self.subTest(value=value):
                with self.assertRaises(error):
                    Namespace(self.ns).getNode(value)

    def test_remove_delete_contents(self):
        """deleteContents=True は内容と子名前空間を削除して None を返し、Undo 1回で戻る。"""
        self._tree()
        target = ":" + self.ns + ":a"
        inner = cmds.createNode("transform", name=target + ":b:inner", skipSelect=True)
        node = cmds.createNode("transform", name=target + ":node", skipSelect=True)
        self.flushUndo()
        self.assertIsNone(Namespace(target).remove(deleteContents=True))

        def after():
            self.assertFalse(cmds.namespace(exists=target))
            self.assertFalse(cmds.objExists(node) or cmds.objExists(inner))

        def before():
            self.assertTrue(cmds.namespace(exists=target))
            self.assertTrue(cmds.objExists(node) and cmds.objExists(inner))
        self.assertUndoesInOneStep(before, after)
        for args, flags, error in (((), {"deleteContents": 1}, TypeError), ((), {"deleteContents": True}, RuntimeError)):
            with self.subTest(flags=flags):
                with self.assertRaises(error):
                    Namespace(":" + self.ns + ":missing").remove(*args, **flags)
        with self.assertRaises(ValueError):
            Namespace(":").remove(deleteContents=True)


class UnitsTest(unittest.TestCase):
    """units.convertTime・convertAngle。"""

    def setUp(self):
        self.time_unit = cmds.currentUnit(query=True, time=True)
        self.angle_unit = cmds.currentUnit(query=True, angle=True)

    def tearDown(self):
        cmds.currentUnit(time=self.time_unit)
        cmds.currentUnit(angle=self.angle_unit)

    def test_convert_time(self):
        """秒・フレーム・Maya の時間単位名の相互変換。None/frame は現在のUI時間単位。"""
        cmds.currentUnit(time="film")
        self.assertAlmostEqual(units.convertTime(48), 48.0)
        self.assertAlmostEqual(units.convertTime(48, toUnit="sec"), 2.0)
        self.assertAlmostEqual(units.convertTime(2, "seconds", "frame"), 48.0)
        self.assertAlmostEqual(units.convertTime(30, "ntsc", "pal"), 25.0)
        self.assertAlmostEqual(units.convertTime(1, "sec", "60fps"), 60.0)
        self.assertAlmostEqual(units.convertTime(1, "min", "sec"), 60.0)
        self.assertAlmostEqual(units.convertTime(1, "sec", "23.976fps"), 23.976, places=3)
        cmds.currentUnit(time="ntsc")
        self.assertAlmostEqual(units.convertTime(1, "sec"), 30.0)
        for args, error in (((1, 5), TypeError), ((1, "nope"), ValueError), ((1, None, "7.5fps"), ValueError),
                            ((1, "deg"), ValueError)):
            with self.subTest(args=args):
                with self.assertRaises(error):
                    units.convertTime(*args)

    def test_convert_angle(self):
        """既定は度→ラジアン。None は現在のUI角度単位。"""
        self.assertAlmostEqual(units.convertAngle(180), math.pi)
        self.assertAlmostEqual(units.convertAngle(math.pi, "rad", "deg"), 180.0)
        self.assertAlmostEqual(units.convertAngle(90, "degrees", "radians"), math.pi / 2)
        cmds.currentUnit(angle="rad")
        self.assertAlmostEqual(units.convertAngle(1.0, None, "deg"), math.degrees(1.0))
        cmds.currentUnit(angle="deg")
        self.assertAlmostEqual(units.convertAngle(math.pi, "rad", None), 180.0)
        for args, error in (((1, 5), TypeError), ((1, "sec"), ValueError), ((1, "deg", "grad"), ValueError)):
            with self.subTest(args=args):
                with self.assertRaises(error):
                    units.convertAngle(*args)


class ReferenceTest(_Case):
    """Reference の追加メソッドと、リファレンス由来の Node・Plug の照会。現在のシーンは開き直さない。"""

    def setUp(self):
        super().setUp()
        self.tmp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp_dir, True)
        self.references = []
        token = uuid.uuid4().hex[:8]
        self.asset = "mlibV124asset_" + token
        self.driven = "mlibV124driven_" + token
        self.path_a = self._export("a.ma", [self.asset, self.driven], connect=True)
        self.path_b = self._export("b.ma", [self.asset, "mlibV124extra_" + token])

    def tearDown(self):
        for reference in self.references:
            if cmds.objExists(reference):
                cmds.file(removeReference=True, referenceNode=reference)
        super().tearDown()

    def _export(self, filename, names, connect=False):
        """ルートに names の transform を作って書き出し、削除してパスを返す。"""
        path = os.path.join(self.tmp_dir, filename).replace("\\", "/")
        created = [cmds.createNode("transform", name=name, skipSelect=True) for name in names]
        if connect:
            cmds.connectAttr(created[0] + ".tx", created[1] + ".ty")
        cmds.select(created, replace=True)
        cmds.file(path, exportSelected=True, type="mayaAscii", force=True)
        cmds.delete(created)
        cmds.select(clear=True)
        return path

    def _reference(self, path, suffix):
        """path をリファレンスし、Reference を返す。"""
        namespace = self.ns + "_" + suffix
        self.extra_namespaces.append(namespace)
        nodes = cmds.file(path, reference=True, namespace=namespace, returnNewNodes=True)
        name = cmds.referenceQuery(nodes[0], referenceNode=True)
        self.references.append(name)
        return mlib.getNode(name)

    def test_queries(self):
        """コピー番号・名前空間の使用・保留の照会と、Node.getReference・Plug.isFromReferencedFile。"""
        first = self._reference(self.path_a, "r1")
        second = self._reference(self.path_a, "r2")
        self.assertIsInstance(first, Reference)
        self.assertEqual(first.getCopyNumber(), 0)
        self.assertEqual(second.getCopyNumber(), 1)
        self.assertTrue(first.isUsingNamespaces())
        self.assertFalse(first.isDeferred())
        asset = mlib.getNode(self.ns + "_r1:" + self.asset)
        driven = mlib.getNode(self.ns + "_r1:" + self.driven)
        self.assertEqual(asset.getReference().getFullName(), first.getFullName())
        self.assertIsNone(mlib.getNode(self.make("transform")).getReference())
        self.assertTrue(driven.ty.isFromReferencedFile())
        self.assertFalse(driven.tz.isFromReferencedFile())
        local = self.make("transform", "local#")
        cmds.connectAttr(asset.getFullName() + ".tz", local + ".tx")
        self.assertFalse(mlib.getPlug(local + ".tx").isFromReferencedFile())
        second.unload()
        self.assertEqual(second.isDeferred(), cmds.file(cmds.referenceQuery(second.getFullName(), filename=True),
                                                        query=True, deferReference=True))

    def test_remove_edits(self):
        """コマンドで絞って削除し、ロード中の適用済み Edit も消える(ロード状態は保つ)。"""
        reference = self._reference(self.path_a, "r1")
        asset = self.ns + "_r1:" + self.asset
        cmds.setAttr(asset + ".tz", 5.0)
        local = self.make("transform", "local#")
        cmds.connectAttr(asset + ".tx", local + ".tx")
        self.assertIs(reference.removeEdits(editCommand="setAttr"), reference)
        self.assertTrue(reference.isLoaded())
        edits = reference.getEditStrings()
        self.assertFalse([edit for edit in edits if edit.startswith("setAttr")])
        self.assertTrue([edit for edit in edits if edit.startswith("connectAttr")])
        self.assertEqual(cmds.getAttr(asset + ".tz"), 0.0)
        reference.removeEdits()
        self.assertEqual(reference.getEditStrings(), [])
        for flags, error in (({"successful": 1}, TypeError), ({"editCommand": 3}, TypeError),
                             ({"editCommand": ""}, ValueError)):
            with self.subTest(flags=flags):
                with self.assertRaises(error):
                    reference.removeEdits(**flags)

    def test_replace_file(self):
        """別のファイルへ置き換え、名前空間を保つ。不正な path は例外。"""
        reference = self._reference(self.path_a, "r1")
        self.assertIs(reference.replaceFile(self.path_b), reference)
        self.assertEqual(os.path.normcase(reference.getFilename()), os.path.normcase(self.path_b))
        self.assertTrue(cmds.objExists(self.ns + "_r1:mlibV124extra_" + self.asset.rsplit("_", 1)[-1]))
        self.assertFalse(cmds.objExists(self.ns + "_r1:" + self.driven))
        for value, error in ((1, TypeError), ("", ValueError),
                             (os.path.join(self.tmp_dir, "missing.ma"), RuntimeError)):
            with self.subTest(value=value):
                with self.assertRaises(error):
                    reference.replaceFile(value)

    def test_import_contents(self):
        """読み込んだノードを返してリファレンスを解除する。removeNamespace=True は名前空間を親へ移す。"""
        reference = self._reference(self.path_a, "r1")
        name = reference.getFullName()
        nodes = reference.importContents()
        self.assertFalse(cmds.objExists(name))
        self.assertIn(self.ns + "_r1:" + self.asset, [node.getNodeName() for node in nodes])
        self.assertFalse(mlib.getNode(self.ns + "_r1:" + self.asset).isFromReferencedFile())
        second = self._reference(self.path_a, "r2")
        imported = second.importContents(removeNamespace=True)
        self.assertFalse(cmds.namespace(exists=":" + self.ns + "_r2"))
        names = [node.getNodeName() for node in imported]
        self.assertIn(self.asset, names)
        for node in imported:
            if node.isValid() and not node.isDefaultNode():
                try:
                    cmds.delete(node.getFullName())
                except RuntimeError:
                    pass
        third = self._reference(self.path_a, "r3")
        third.unload()
        with self.assertRaises(RuntimeError):
            third.importContents()
        with self.assertRaises(TypeError):
            third.importContents(removeNamespace=1)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
