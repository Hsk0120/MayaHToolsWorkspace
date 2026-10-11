"""コーンの一致度(0〜1)の数値・追従・表示・Undoを検証する。"""

import math
import unittest

from maya import cmds

from mlrig.setups import ConeReader


def _axis(node, index=0):
    """transformのワールド軸(0=X,1=Y,2=Z)を正規化して返す。"""
    m = cmds.xform(node, query=True, worldSpace=True, matrix=True)
    v = m[index*4:index*4+3]
    n = math.sqrt(sum(x*x for x in v))
    return [x/n for x in v]


def _angle(a, b):
    """二つの単位ベクトルのなす角。度。"""
    return math.degrees(math.acos(max(-1.0, min(1.0, sum(x*y for x, y in zip(a, b))))))


class ConeReaderTest(unittest.TestCase):
    """標準ノードの実評価結果を、独立に求めた値と比べる。"""

    def setUp(self):
        """肩と上腕のジョイントを持つ空シーンを作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.shoulder = cmds.createNode("joint", name="shoulder")
        self.arm = cmds.createNode("joint", name="upperArm", parent=self.shoulder)
        cmds.setAttr(self.arm+".tx", 2)

    def _weight(self, reader):
        return reader.container.getPlug("weight").get()

    def test_rest_center_and_edge(self):
        """作成直後は1、半角の半分で0.5、半角以上で0になる。"""
        reader = ConeReader.create(self.arm, self.shoulder, name="reader", coneAngle=60)
        self.assertAlmostEqual(self._weight(reader), 1, places=5)
        for attr, value, expected in (("rz", 30, 0.5), ("rz", -30, 0.5), ("ry", 30, 0.5),
                                      ("rz", 60, 0), ("rz", 90, 0), ("rx", 70, 1)):
            cmds.setAttr(self.arm+".rotate", 0, 0, 0)
            cmds.setAttr(self.arm+"."+attr, value)
            self.assertAlmostEqual(self._weight(reader), expected, places=4, msg=(attr, value))
            angle = _angle(_axis(reader.driver), _axis(reader.cone))
            self.assertAlmostEqual(reader.container.getPlug("angle").get(), angle, places=3)

    def test_matches_independent_calculation(self):
        """複合回転・コーンの向き・半角を変えても、独立計算と一致する。"""
        reader = ConeReader.create(self.arm, self.shoulder, name="reader", coneAngle=45)
        cmds.setAttr(reader.cone+".rotate", 0, 35, 10)
        for cone_angle in (20, 45, 120):
            reader.container.getPlug("coneAngle").set(cone_angle)
            for rotation in ((0, 0, 0), (10, 20, 30), (-40, 15, 60), (90, -30, 0)):
                cmds.setAttr(self.arm+".rotate", *rotation)
                angle = _angle(_axis(reader.driver), _axis(reader.cone))
                self.assertAlmostEqual(self._weight(reader), ConeReader.weight(angle, cone_angle), places=4)

    def test_follows_cone_joint(self):
        """コーンを追従させたジョイントを回すと、コーンも一緒に回る。"""
        reader = ConeReader.create(self.arm, self.shoulder, name="reader", coneAngle=40)
        cmds.setAttr(self.shoulder+".rotate", 30, -20, 45)
        self.assertAlmostEqual(self._weight(reader), 1, places=4)
        cmds.setAttr(self.arm+".rz", 20)
        self.assertAlmostEqual(self._weight(reader), 0.5, places=4)

    def test_smooth_falloff(self):
        """smooth は t²(3-2t)。中心・半分・端で既知の値になる。"""
        reader = ConeReader.create(self.arm, self.shoulder, name="reader", coneAngle=60, falloff="smooth")
        for value, expected in ((0, 1), (15, 0.84375), (30, 0.5), (60, 0)):
            cmds.setAttr(self.arm+".rz", value)
            self.assertAlmostEqual(self._weight(reader), expected, places=4)
        reader.container.getPlug("falloff").set(0)
        cmds.setAttr(self.arm+".rz", 15)
        self.assertAlmostEqual(self._weight(reader), 0.75, places=4)

    def test_driver_axis_and_without_joints(self):
        """driverAxis で矢印の軸を選べる。ジョイントなしでも作れる。"""
        reader = ConeReader.create(self.arm, name="axisY", driverAxis="y")
        for a, b in zip(_axis(reader.driver), _axis(self.arm, 1)):
            self.assertAlmostEqual(a, b, places=5)
        free = ConeReader.create(name="free", coneAngle=90)
        self.assertAlmostEqual(self._weight(free), 1, places=5)
        cmds.setAttr(free.driver+".ry", 45)
        self.assertAlmostEqual(self._weight(free), 0.5, places=4)

    def test_display_follows_cone_angle(self):
        """コーンの表示は x 方向 cosγ·size、yz 方向 sinγ·size になる。"""
        reader = ConeReader.create(self.arm, self.shoulder, name="reader", coneAngle=30, size=2)
        display = reader.cone+"|reader_coneDisplay" if cmds.objExists(reader.cone+"|reader_coneDisplay") \
            else "reader_coneDisplay"
        for cone_angle in (30, 120):
            reader.container.getPlug("coneAngle").set(cone_angle)
            scale = cmds.getAttr(display+".scale")[0]
            self.assertAlmostEqual(scale[0], 2*math.cos(math.radians(cone_angle)), places=4)
            self.assertAlmostEqual(scale[1], 2*math.sin(math.radians(cone_angle)), places=4)
            self.assertAlmostEqual(scale[2], 2*math.sin(math.radians(cone_angle)), places=4)
        self.assertAlmostEqual(cmds.getAttr("reader_driverDisplay.scaleX"), 2, places=5)

    def test_validation_and_undo(self):
        """不正な入力を拒否し、作成を一回のUndoで戻せる。"""
        with self.assertRaises(ValueError):
            ConeReader.create(self.arm, name="bad", coneAngle=0)
        with self.assertRaises(ValueError):
            ConeReader.create(self.arm, name="bad", driverAxis="w")
        with self.assertRaises(ValueError):
            ConeReader.create("missingJoint", name="bad")
        with self.assertRaises(ValueError):
            ConeReader.weight(10, 30, falloff="cubic")
        cmds.undoInfo(state=True)
        cmds.flushUndo()
        ConeReader.create(self.arm, self.shoulder, name="undoReader")
        self.assertTrue(cmds.objExists("undoReader"))
        with self.assertRaises(ValueError):
            ConeReader.create(self.arm, name="undoReader")
        cmds.undo()
        for node in ("undoReader", "undoReader_driver_GRP", "undoReader_cone_GRP"):
            self.assertFalse(cmds.objExists(node), node)


if __name__ == "__main__":
    unittest.main(argv=["cone_reader"], exit=False, verbosity=2)
