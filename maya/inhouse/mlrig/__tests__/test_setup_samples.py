"""mlrigメニューの「Setup Samples」から呼ぶサンプルを、mayapyで作成・操作・Undoして確かめる。

メニューの表示(cmds.menuItem)はGUIでしか作れないため、項目が呼ぶ ``Menu.run("setup:<種類>")`` と
:class:`mlrig.setupSamples.SetupSamples` を直接試験する。
"""

import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.menu import Menu
from mlrig.setupSamples import SetupSamples


def _set(attribute, value):
    """アトリビュートへ値を入れる関数を返す。"""
    def apply(sample):
        node = sample.target if attribute.startswith(".") else ""
        cmds.setAttr(node + attribute, value)
    return apply


def _add(attribute, value):
    """アトリビュートへ値を足す関数を返す。"""
    def apply(sample):
        plug = sample.target + attribute
        cmds.setAttr(plug, cmds.getAttr(plug) + value)
    return apply


def _moveCv(sample):
    """曲線のCVを1つ動かす。"""
    cmds.move(0, 2, 1, sample.target + ".cv[3]", relative=True)


#: 種類ごとの (対象を動かす関数, 変化を確かめるノードの名前の末尾、またはcontainerのアトリビュート)。
CHANGES = {
    "hingeIK": (_add(".translateY", 2.0), "_knee"),
    "planarIK": (_add(".translateY", 2.0), "_knee"),
    "poleVectorPlacement": (_set(".rotateY", 70.0), "_pole_loc"),
    "noFlipPole": (_set(".rotateY", 40.0), "_pole"),
    "limbPin": (_add(".translateY", 2.0), "_elbow"),
    "eyelidFollow": (_set(".rotateX", 20.0), "_upperLidOut"),
    "jawHinge": (_set(".rotateX", 20.0), "_jawOut"),
    "piston": (_set(".rotateZ", 60.0), "_rodOut"),
    "bowString": (_set(".translateZ", 4.0), "_topStringOut"),
    "waveChain": (_set(".phase", 90.0), "_tail3Out"),
    "waveFloat": (_add(".translateX", 3.0), "_boatOut"),
    "wheelRoll": (_set(".translateZ", 3.0), "_wheelOut"),
    "gearTrain": (_set(".rotateZ", 45.0), "_gear3"),
    "ackermannSteering": (_set(".rotateZ", -240.0), "_frontLeft"),
    "treadBelt": (_add(".translateZ", 2.0), "_plate0Out"),
    "rockerRoll": (_set(".roll", 20.0), "_rockerOut"),
    "outlineBank": (_set(".rotateZ", -20.0), "_boxOut"),
    "crankSlider": (_set(".rotateZ", 120.0), "_pistonOut"),
    "fourBarLinkage": (_set(".rotateZ", 120.0), "_rockerOut"),
    "scissorLift": (_set(".height", 12.0), "_platformOut"),
    "cableSag": (_add(".translateX", -2.0), "_cable4Out"),
    "rotationMinimizingFrames": (_add(".translateY", 2.0), "_frame1Out"),
    "rotationMinimizingFramesCurve": (_moveCv, "_frame3Out"),
    "ribbon": (_add(".translateY", 2.0), "_ribbon3Out"),
    "chainNet": (_set(".rotateZ", 40.0), "_slave0_3"),
    "leafJoints": (_set(".scaleY", 2.2), "_leaf1"),
    "bodyProportion": (_set(".armLength", 1.0), "_wristL"),
    "metaSpread": (_set(".rotateY", -30.0), "_meta2Out"),
    "neckHeadSplit": (_set(".rotateZ", 40.0), "_neck2Out"),
    "footRoll": (_set(".roll", 40.0), "_ankleOut"),
    "muscleBulge": (_set(".rotateZ", 120.0), "_bulgeOut"),
    "pumpUp": (_set(".translateY", 1.0), "_pumpOut"),
    "groundTilt": (_add(".translateY", 1.5), "_bodyOut"),
    "centerOfMass": (_set(".rotateX", 40.0), "_comOut"),
    "skirtLegOffset": (_set(".rotateX", -60.0), "_skirt0"),
    "lipZip": (_set(".zipLeft", 0.6), "_upper4Out"),
    "squashBox": (_set(".top", 1.5), "_boxOut"),
    "planeCollision": (_add(".translateY", -3.0), "_footOut"),
    "sphereCollision": (_add(".translateX", -5.0), "_handOut"),
    "capsuleCollision": (_add(".translateX", -4.0), "_skirtOut"),
    "spaceBlend": (_add(".translateY", 2.0), "_ctrlOut"),
    "cameraAngleReader": (_add(".translateX", 15.0), ".weightLeft"),
    "dollyZoom": (_add(".translateZ", -10.0), ".focalLength"),
    "overShoulderCamera": (_add(".translateX", 3.0), "_cameraOut"),
    "liveMirror": (_set(".rotateZ", 50.0), "_handR"),
    "eyeHighlight": (_add(".translateX", 4.0), "_leftHighlightOut"),
    "unevenGround": (_add(".translateY", 1.0), "_leftFootOut"),
    "hipSwing": (_set(".rotateZ", 30.0), "_hipsOut"),
    "boxRoll": (_set(".roll", 120.0), "_boxOut"),
    "uiSlider": (_add(".translateX", 1.0), ".right"),
    "comboWeight": (_set(".translateY", 1.0), ".both"),
    "virtualChain": (_set(".rotateZ", 30.0), "_ctrl3"),
    "stickyControl": (_set(".rotateX", 30.0), "_ctrl"),
    "fkIkChain": (_add(".translateY", 3.0), "_tail4Out"),
    "slidingFk": (_set(".rotateZ", 40.0), "_tail3Out"),
    "swingLimit": (_set(".rotateZ", 80.0), "_out"),
    "asymmetricSwingLimit": (_set(".rotateZ", 80.0), "_out"),
    "twistLimit": (_set(".rotateX", 80.0), "_out"),
    "swingTwist": (_set(".rotateZ", 40.0), "_out"),
    "rotationFollow": (_set(".rotateZ", 40.0), "_out"),
    "coneReader": (_set(".rotateZ", 60.0), ".weight"),
}


#: 作成直後に、出力(緑)が入力と同じワールド行列になる組 (出力の名前の末尾, 入力の名前の末尾)。
#: WaveChainのサンプルは波が見えるよう振幅20度で作るため、作成直後から出力が入力と異なり、対象外。
#: WaveFloatのサンプルも波が見えるよう振幅を入れて時刻へ接続するため、作成直後から出力が入力と異なり、対象外
#: (振幅0では作成時に跳ねないことは test_setup_wave_float で確認する)。
#: MuscleBulgeの出力は上腕の途中に置く補助骨で、入力のjointと同じ位置にはならないため対象外
#: (作成直後に膨らまないことは test_setup_muscle_bulge で確認する)。
#: NoFlipPoleの出力はポールの位置、GearTrainの出力は歯車そのものなので対象外(作成直後に膝・歯車が
#: 跳ねないことは test_setup_no_flip_pole・test_setup_gear_train で確認する)。
#: TreadBeltの出力は曲線の上を巡回する板で、対応する入力のノードが無いため対象外(作成時に driver の変化量0で
#: 板が動かないことは test_setup_tread_belt で確認する)。
#: SkirtLegOffsetの出力はスカートの骨そのもの(offsetParentMatrixへ接続)なので対象外(作成直後に骨が
#: 動かないことは test_setup_skirt_leg_offset で確認する)。
#: ChainNetの出力も子チェーンの節そのもの(offsetParentMatrixへ接続)なので対象外(作成直後に節が
#: 動かないことは test_setup_chain_net で確認する)。
#: CableSagの出力は垂れたケーブルの上の点で、対応する入力のノードが無いため対象外(両端の点が留め具と
#: 一致することは test_setup_cable_sag で確認する)。
#: LimbPinの出力は元の腕のjointの長さそのもので、肘・手首の位置は極ベクトルの操作子・目標と一致するが向きは
#: 一致しないため対象外(作成直後に腕が跳ねないこと・pin=1 で肘が操作子へ来ることは test_setup_limb_pin で確認する)。
#: AckermannSteeringの出力は前輪そのもの(rotateYへ接続)なので対象外(作成直後に車輪が跳ねないことは
#: test_setup_ackermann_steering で確認する)。
#: ScissorLiftの出力は台の高さから作る腕・台・滑る足で、対応する入力のノードが無いため対象外(作成直後の
#: 腕の両端が段の支点に乗ることは test_setup_scissor_lift で確認する)。
#: BodyProportionの出力は体格調整用の骨そのもの(translate・scaleへ接続)なので対象外(作成直後に骨が
#: 動かないことは test_setup_body_proportion で確認する)。
#: ComboWeightの出力はウェイトの値(口のブレンドシェイプのウェイトへ接続)で、対応する入力のノードが無いため
#: 対象外(値の式とブレンドシェイプでの補正は test_setup_combo_weight で確認する)。
#: VirtualChainの出力はコントロールそのもの(offsetParentMatrixへ接続)なので対象外(作成直後にコントロールが
#: 動かないこと・本物の階層との一致は test_setup_virtual_chain で確認する)。
#: CenterOfMassの出力は全身の重心(体節の点の加重平均)で、対応する入力のノードが無いため対象外(重心の式との
#: 一致は test_setup_center_of_mass で確認する)。
#: DollyZoomの出力はカメラの焦点距離(値)で、対応する入力のノードが無いため対象外(作成直後に焦点距離が
#: 変わらないことは test_setup_dolly_zoom で確認する)。
#: OverShoulderCameraの出力はカメラの配置(2人の頭から決まる)で、対応する入力のノードが無いため対象外(既定の
#: weight=0で作成直後にカメラが動かないことは test_setup_over_shoulder_camera で確認する)。
#: LiveMirrorの出力は右のjoint(左の鏡像)で、入力と同じワールド行列にはならないため対象外(作成直後に
#: 右が動かないこと・鏡像の式との一致は test_setup_live_mirror で確認する)。
#: EyeHighlightの出力は眼球の表面のハイライトで、対応する入力のノードが無いため対象外(既定の weight=0 で
#: 作成直後にハイライトが動かないこと・式との一致は test_setup_eye_highlight で確認する)。
#: UnevenGroundのサンプルは凹凸のある地面で作るため、作成直後から足・腰の出力が入力と異なり、対象外(地面が
#: 床の高さで水平なら作成直後に出力が入力と同じことは test_setup_uneven_ground で確認する)。
REST_MATCH = {
    "hipSwing": ("_hipsOut", "_hips"),
    "boxRoll": ("_boxOut", "_box"),
    "leafJoints": ("_leaf1", "_elbow"),
    "eyelidFollow": ("_upperLidOut", "_upperLid"),
    "jawHinge": ("_jawOut", "_jaw"),
    "piston": ("_rodOut", "_rod"),
    "bowString": ("_topStringOut", "_top"),
    "wheelRoll": ("_wheelOut", "_wheel"),
    "rockerRoll": ("_rockerOut", "_rocker"),
    "outlineBank": ("_boxOut", "_ctrl"),
    "crankSlider": ("_pistonOut", "_piston"),
    "fourBarLinkage": ("_rockerOut", "_rocker"),
    "ribbon": ("_ribbon0Out", "_ctrl0"),
    "metaSpread": ("_meta1Out", "_meta1"),
    "neckHeadSplit": ("_headOut", "_head"),
    "footRoll": ("_ankleOut", "_ankle"),
    "groundTilt": ("_bodyOut", "_bodyCtrl"),
    "pumpUp": ("_pumpOut", "_bulge"),
    "lipZip": ("_upper2Out", "_upper2"),
    "squashBox": ("_boxOut", "_boxCtrl"),
    "planeCollision": ("_footOut", "_footCtrl"),
    "sphereCollision": ("_handOut", "_handCtrl"),
    "capsuleCollision": ("_skirtOut", "_skirtCtrl"),
    "spaceBlend": ("_ctrlOut", "_ctrl"),
    "fkIkChain": ("_tail4Out", "_fk4"),
    "slidingFk": ("_tail3Out", "_tail3"),
    "swingLimit": ("_out", "_input"),
    "asymmetricSwingLimit": ("_out", "_input"),
    "twistLimit": ("_out", "_input"),
    "swingTwist": ("_out", "_input"),
    "rotationFollow": ("_out", "_input"),
}


def _watch(sample, suffix):
    """変化を確かめる値。ノードならワールド行列、containerのアトリビュートなら値。"""
    if suffix.startswith("."):
        return [cmds.getAttr(sample.container + suffix)]
    name = sample.root.rsplit("|", 1)[-1][:-len("_sample_grp")] + suffix
    nodes = cmds.ls(name, long=True)
    if len(nodes) != 1:
        raise AssertionError("Expected one node named " + name + ": " + str(nodes))
    return list(om.MMatrix(cmds.getAttr(nodes[0] + ".worldMatrix[0]")))


def _sceneNodes():
    """シーンのノード名の集合。初回のikHandleでMayaが作る共通のsolver(Undoで消えない)は除く。"""
    return set(cmds.ls()) - set(cmds.ls(type=("ikSolver", "hikSolver")))


def _different(before, after, tolerance=1e-4):
    """2つの値の列が誤差より大きく違うか。"""
    return any(abs(a - b) > tolerance for a, b in zip(before, after))


class SetupSamplesTest(unittest.TestCase):
    """全サンプルの作成・入力の操作による出力の変化・Undo・名前の連番・メニュー経由の実行を確認する。"""

    def setUp(self):
        """空のシーンにする。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")

    def test_items_have_checks(self):
        """メニューの全項目に、この試験の確認内容がある(項目を足したら試験も足す)。"""
        self.assertEqual(sorted(SetupSamples.kinds()), sorted(CHANGES))
        self.assertEqual(len(set(SetupSamples.kinds())), len(SetupSamples.ITEMS))
        for kind, label in SetupSamples.ITEMS:
            self.assertTrue(label.isascii(), label)
            self.assertEqual(SetupSamples.label(kind), label)

    def test_build_and_drive(self):
        """各サンプルを作ると対象とcontainerがあり、対象を動かすと出力が変わる。"""
        for kind in SetupSamples.kinds():
            with self.subTest(kind=kind):
                cmds.file(new=True, force=True)
                sample = SetupSamples.build(kind)
                self.assertTrue(cmds.objExists(sample.root))
                self.assertTrue(cmds.objExists(sample.target), sample.target)
                self.assertEqual(cmds.nodeType(sample.container), "container")
                if kind in REST_MATCH:
                    output, source = (_watch(sample, suffix) for suffix in REST_MATCH[kind])
                    self.assertFalse(_different(output, source), kind)
                change, suffix = CHANGES[kind]
                before = _watch(sample, suffix)
                change(sample)
                after = _watch(sample, suffix)
                self.assertTrue(_different(before, after), (kind, before, after))

    def test_undo_removes_sample(self):
        """1回のUndoでサンプル全体が消え、Redoで戻る。"""
        for kind in SetupSamples.kinds():
            with self.subTest(kind=kind):
                cmds.file(new=True, force=True)
                cmds.undoInfo(state=True, infinity=True)
                before = _sceneNodes()
                sample = SetupSamples.build(kind)
                created = _sceneNodes() - before
                self.assertTrue(created)
                cmds.undo()
                self.assertEqual(_sceneNodes(), before)
                cmds.redo()
                self.assertTrue(cmds.objExists(sample.root))
                self.assertTrue(cmds.objExists(sample.container))

    def test_names_do_not_collide(self):
        """同じ種類を2回作ると、別の連番の名前になる。"""
        for kind in ("hingeIK", "waveChain", "coneReader"):
            with self.subTest(kind=kind):
                first = SetupSamples.build(kind)
                second = SetupSamples.build(kind)
                self.assertNotEqual(first.root, second.root)
                self.assertNotEqual(first.container, second.container)
                self.assertTrue(first.container.endswith(kind + "1"), first.container)
                self.assertTrue(second.container.endswith(kind + "2"), second.container)

    def test_bad_arguments(self):
        """未知の種類と使用済みの名前は、何も作らずにValueErrorになる。"""
        SetupSamples.build("swingLimit", name="taken")
        before = _sceneNodes()
        with self.assertRaises(ValueError):
            SetupSamples.build("unknownSample")
        with self.assertRaises(ValueError):
            SetupSamples.build("twistLimit", name="taken")
        self.assertEqual(_sceneNodes(), before)

    def test_menu_run(self):
        """メニューの項目が呼ぶ ``Menu.run`` でサンプルが作られ、動かす対象が選択される。"""
        for kind in SetupSamples.kinds():
            with self.subTest(kind=kind):
                cmds.file(new=True, force=True)
                sample = Menu.run("setup:" + kind)
                self.assertIsNotNone(sample, kind)
                self.assertEqual(cmds.ls(selection=True, long=True), [sample.target])


if __name__ == "__main__":
    unittest.main(argv=["setupSamples"], exit=False, verbosity=2)
