"""mlrigメニューから ``mlrig.setups`` の各セットアップを試すためのサンプル。

各サンプルは現在のシーンへ、``<名前>_sample_grp`` の下にまとめた小さな入力(joint・transform)と、
セットアップの出力を受ける緑の結果jointを作る。新規シーンは作らず、1回のUndoで全体を取り消せる。
既存のサンプル作成(:class:`mlrig.sampleBuilder.SampleBuilder`)と同じく、名前は既存のノードと
重ならない連番を使う。表示用の色は、入力を既定の色、出力を緑(indexの14)にする。
"""

import math

import mlib
from mlib.decorator import undoTransaction

#: 出力(セットアップの結果)を示す色。Mayaの表示色のindex。
_OUTPUT_COLOR = 14


class SetupSample:
    """生成したサンプルの主なノードをまとめる。

    Attributes:
        root (str): サンプル全体をまとめたtransformのフルパス。
        target (str): 選択して動かすノード(ikHandle・入力joint・containerなど)。
        container (str): セットアップのcontainer。
        setup (object): セットアップの ``create`` が返した生成結果。
    """

    def __init__(self, root, target, container, setup):
        """生成結果をまとめる。

        Args:
            root (str): まとめのtransform。
            target (str): 選択して動かすノード。
            container (str): セットアップのcontainer。
            setup (object): セットアップの生成結果。
        """
        self.root = root
        self.target = target
        self.container = container
        self.setup = setup


class SetupSamples:
    """セットアップのサンプルを種類ごとに作る入口。メニューと試験から共通に使う。"""

    #: (種類のID, メニューの表示名)。メニューはこの順に並べる。
    ITEMS = (
        ("hingeIK", "HingeIK - offset knee leg"),
        ("planarIK", "PlanarIK - leg with offset bones"),
        ("poleVectorPlacement", "PoleVectorPlacement - arm"),
        ("noFlipPole", "NoFlipPole - leg with foot-driven knee"),
        ("limbPin", "LimbPin - arm with elbow pin and slide"),
        ("eyelidFollow", "EyelidFollow - eye and lids"),
        ("jawHinge", "JawHinge - jaw"),
        ("piston", "Piston - cylinder and rod"),
        ("bowString", "BowString - bow and nock"),
        ("waveChain", "WaveChain - tail wave"),
        ("waveFloat", "WaveFloat - boat on waves"),
        ("wheelRoll", "WheelRoll - wheel"),
        ("gearTrain", "GearTrain - four gears"),
        ("ackermannSteering", "AckermannSteering - car front wheels"),
        ("treadBelt", "TreadBelt - tank tread"),
        ("rockerRoll", "RockerRoll - rocking chair runner"),
        ("outlineBank", "OutlineBank - box tilting on its base outline"),
        ("crankSlider", "CrankSlider - engine crank and piston"),
        ("fourBarLinkage", "FourBarLinkage - crank, coupler and rocker"),
        ("scissorLift", "ScissorLift - three-stage scissor lift"),
        ("cableSag", "CableSag - hanging cable between two posts"),
        ("rotationMinimizingFrames", "RotationMinimizingFrames - points"),
        ("rotationMinimizingFramesCurve", "RotationMinimizingFrames - curve"),
        ("ribbon", "Ribbon - five controls"),
        ("chainNet", "ChainNet - fin with two master chains"),
        ("leafJoints", "LeafJoints - squash arm for export"),
        ("bodyProportion", "BodyProportion - body shape parameters"),
        ("metaSpread", "MetaSpread - palm metacarpals"),
        ("neckHeadSplit", "NeckHeadSplit - head control shared by the neck"),
        ("footRoll", "FootRoll - reverse foot"),
        ("muscleBulge", "MuscleBulge - biceps"),
        ("pumpUp", "PumpUp - amplify the biceps helper"),
        ("groundTilt", "GroundTilt - four feet"),
        ("centerOfMass", "CenterOfMass - stick figure balance"),
        ("skirtLegOffset", "SkirtLegOffset - skirt and two legs"),
        ("lipZip", "LipZip - sticky lips"),
        ("squashBox", "SquashBox - four sides"),
        ("planeCollision", "PlaneCollision - soft floor"),
        ("sphereCollision", "SphereCollision - soft head collider"),
        ("capsuleCollision", "CapsuleCollision - soft thigh collider"),
        ("ellipsoidCollision", "EllipsoidCollision - soft chest collider"),
        ("boxCollision", "BoxCollision - soft rounded table edge"),
        ("spaceBlend", "SpaceBlend - world, chest and hand"),
        ("cameraAngleReader", "CameraAngleReader - face and camera"),
        ("dollyZoom", "DollyZoom - camera keeps the subject size"),
        ("overShoulderCamera", "OverShoulderCamera - conversation shot"),
        ("liveMirror", "LiveMirror - mirror left arm pose to the right"),
        ("eyeHighlight", "EyeHighlight - catchlight follows the camera"),
        ("unevenGround", "UnevenGround - feet and hips on a slope and a step"),
        ("hipSwing", "HipSwing - swing the hips, keep the chest"),
        ("boxRoll", "BoxRoll - box tumbles edge over edge"),
        ("uiSlider", "UiSlider - face panel slider"),
        ("comboWeight", "ComboWeight - smile combo corrective"),
        ("virtualChain", "VirtualChain - flat tail controls as FK"),
        ("stickyControl", "StickyControl - control on a skinned surface"),
        ("fkIkChain", "FkIkChain - tail FK/IK blend"),
        ("slidingFk", "SlidingFk - tail with two sliding controls"),
        ("swingLimit", "SwingLimit - shoulder"),
        ("asymmetricSwingLimit", "AsymmetricSwingLimit - shoulder"),
        ("twistLimit", "TwistLimit - forearm"),
        ("swingTwist", "SwingTwist - swing only"),
        ("rotationFollow", "RotationFollow - half rotation"),
        ("coneReader", "ConeReader - shoulder cone"),
    )

    @classmethod
    def kinds(cls):
        """サンプルの種類のIDを、メニューの順に返す。

        Returns:
            list[str]: 種類のID。
        """
        return [kind for kind, _ in cls.ITEMS]

    @classmethod
    def label(cls, kind):
        """種類のIDに対応するメニューの表示名を返す。

        Args:
            kind (str): 種類のID。

        Returns:
            str: 表示名(英語)。

        Raises:
            ValueError: 未知の種類の場合。
        """
        for item, text in cls.ITEMS:
            if item == kind:
                return text
        raise ValueError("Unknown setup sample: " + str(kind))

    @classmethod
    def nextName(cls, kind):
        """シーンの既存ノードと重ならないサンプル名を返す。

        Args:
            kind (str): 種類のID。名前の接頭辞にする。

        Returns:
            str: ``<kind><番号>`` の形の名前。
        """
        index = 1
        while mlib.ls(kind + str(index) + "*"):
            index += 1
        return kind + str(index)

    @classmethod
    @undoTransaction("mlrig.SetupSamples.build")
    def build(cls, kind, name=None):
        """サンプルを現在のシーンへ作る。

        Args:
            kind (str): 種類のID(:attr:`ITEMS` の1列目)。
            name (str | None): 名前の接頭辞。Noneなら :meth:`nextName` で決める。

        Returns:
            SetupSample: 生成結果。

        Raises:
            ValueError: 未知の種類の場合、または名前が既に使われている場合。
        """
        cls.label(kind)
        if name is None:
            name = cls.nextName(kind)
        if mlib.ls(name + "*"):
            raise ValueError("Sample name already exists: " + name)
        root = _transform(name + "_sample_grp", None)
        setup, target = getattr(cls, "_" + kind)(name, root)
        container = str(setup.container)
        return SetupSample(root, _longName(target), container, setup)

    # --- 各サンプル ------------------------------------------------------------

    @classmethod
    def _hingeIK(cls, name, root):
        """膝が横にずれた脚。ikHandleを動かすと膝は1軸だけで曲がる。"""
        from .setups import HingeIK

        pelvis = _transform(name + "_pelvis", root)
        hip, knee, ankle = _chain(name, pelvis, (("hip", (0, 10, 0)), ("knee", (1.2, 5, 1.0)),
                                                 ("ankle", (0, 0, 0.5))))
        setup = HingeIK.create(hip, knee, ankle, name=name)
        return setup, setup.handle

    @classmethod
    def _planarIK(cls, name, root):
        """途中にずれた骨がある脚。ikHandleを動かすと元のjointがIK用チェーンに追従する。"""
        from .setups import PlanarIK

        pelvis = _transform(name + "_pelvis", root)
        hip, _, knee, _, ankle = _chain(name, pelvis, (
            ("hip", (0, 10, 0)), ("thighOffset", (2.0, 8.0, 0.5)), ("knee", (1.2, 5.0, 1.0)),
            ("shinOffset", (1.8, 2.5, 1.5)), ("ankle", (0.0, 0.0, 0.5))))
        setup = PlanarIK.create(hip, knee, ankle, name=name)
        return setup, setup.handle

    @classmethod
    def _poleVectorPlacement(cls, name, root):
        """腕の3関節。肘を回すとポールベクターの位置(緑のlocator)が肘の外側へ移る。"""
        from .setups import PoleVectorPlacement

        chest = _transform(name + "_chest", root, translate=(0, 10, 0))
        shoulder = _joint(name + "_shoulder", chest)
        elbow = _joint(name + "_elbow", shoulder, translate=(5, 0, 0))
        wrist = _joint(name + "_wrist", elbow, translate=(5, 0, 0))
        _set(elbow, "rotateY", 40)
        setup = PoleVectorPlacement.create(shoulder, elbow, wrist, name=name, distance=5.0)
        marker = _locator(name + "_pole_loc", root)
        _color(marker)
        _connect(str(setup.container) + ".matrix", marker + ".offsetParentMatrix")
        return setup, elbow

    @classmethod
    def _limbPin(cls, name, root):
        """肩・肘・手首の腕(ikRPsolver)と、肘の位置の極ベクトルの操作子・手首の位置の目標。pin=1 なので
        操作子を動かすと肘がその位置へ留まり、目標を動かすと前腕の長さが変わる。containerの pin を0へ
        下げると元の長さへ戻り、slide で上腕と前腕の長さの比が変わる。"""
        from .setups import LimbPin
        from .setups.hingeIK import createRotatePlaneHandle, storePreferredAngles

        chest = _transform(name + "_chest", root, translate=(0, 8, 0))
        shoulder = _joint(name + "_shoulder", chest, rotate=(0, 20, 0))
        elbow = _joint(name + "_elbow", shoulder, translate=(4, 0, 0), rotate=(0, -40, 0))
        wrist = _joint(name + "_wrist", elbow, translate=(4, 0, 0))
        bend = math.radians(20.0)
        # 曲げた姿勢を優先角度にしてからIKを作る(真っすぐと見なされると肘が曲がらない)。
        storePreferredAngles([shoulder, elbow, wrist])
        handle, _, pole = createRotatePlaneHandle(shoulder, wrist, name)
        # 極ベクトルの操作子を肘の位置へ移す(同じ平面の上なので腕は動かない)。
        pole = mlib.nodes.Node(pole).setParent(root).getFullName()
        _set(pole, "translate", (4 * math.cos(bend), 8, -4 * math.sin(bend)))
        target = _locator(name + "_target", root, translate=(8 * math.cos(bend), 8, 0))
        handle = mlib.nodes.Node(handle).setParent(target).getFullName()
        _set(handle, "translate", (0, 0, 0))
        _set(handle, "visibility", False)
        setup = LimbPin.create(shoulder, elbow, wrist, pole, target, name=name, pin=1.0)
        for joint in (elbow, wrist):
            _color(joint)
        return setup, pole

    @classmethod
    def _noFlipPole(cls, name, root):
        """少し前へ曲がった脚(RP IK)と足のコントロール(locator)。コントロールを動かす・Y回りに回すと、
        ポール(緑のlocator)が足の前の向きに付いて動き、足を股関節の前後へ大きく振っても膝が反転しない。
        containerの ``kneeTwist`` で脚の軸まわりに膝の向きを回せる。"""
        from .setups import NoFlipPole
        from .setups.hingeIK import createRotatePlaneHandle

        pelvis = _transform(name + "_pelvis", root)
        hip, knee, ankle = _chain(name, pelvis, (("hip", (0, 10, 0)), ("knee", (0, 5, 1.0)),
                                                 ("ankle", (0, 0.5, 0.3))))
        control = _locator(name + "_footCtrl", root, translate=(0, 0.5, 0.3))
        handle, _, pole = createRotatePlaneHandle(hip, ankle, name)
        mlib.nodes.Node(handle).setParent(control)
        pole = mlib.nodes.Node(pole)
        pole.setParent(root)
        setup = NoFlipPole.create(hip, control, mid=knee, name=name, distance=6.0)
        pole.getPlug("translate").set((0, 0, 0))
        pole = pole.getFullName()
        _connect(str(setup.container) + ".matrix", pole + ".offsetParentMatrix")
        _color(pole)
        return setup, control

    @classmethod
    def _eyelidFollow(cls, name, root):
        """目と上下のまぶた。目を回すとまぶた(緑)が追従する。"""
        from .setups import EyelidFollow

        socket = _transform(name + "_eyeSocket", root, translate=(0, 10, 0))
        eye = _joint(name + "_eye", socket)
        _tip(eye, name + "_eyeTip", (0, 0, 1.5))
        upper = _joint(name + "_upperLid", socket, rotate=(-20, 0, 0))
        lower = _joint(name + "_lowerLid", socket, rotate=(20, 0, 0))
        setup = EyelidFollow.create(eye, upper, lower, name=name, pitchAxis="x", yawAxis="y")
        for role in ("upper", "lower"):
            _output(name + "_" + role + "LidOut", socket, str(setup.container) + "." + role + "Matrix",
                    ((0, 0, 1.2),))
        return setup, eye

    @classmethod
    def _jawHinge(cls, name, root):
        """顎。顎のrotateXを回すと、閉じ側は柔らかく止まり、開くと前へずれる(緑)。"""
        from .setups import JawHinge

        head = _transform(name + "_head", root, translate=(0, 10, 0))
        jaw = _joint(name + "_jaw", head, translate=(0, -1, 1))
        setup = JawHinge.create(jaw, name=name, pitchAxis="x", yawAxis="y")
        _tip(jaw, name + "_jawTip", (0, -0.5, 3))
        _output(name + "_jawOut", head, str(setup.container) + ".matrix", ((0, -0.5, 3),))
        return setup, jaw

    @classmethod
    def _piston(cls, name, root):
        """アームの先に付いたピストン。アームを回すとシリンダーとロッド(緑)が互いを向く。"""
        import math

        from .setups import Piston

        frame = _transform(name + "_frame", root)
        arm = _transform(name + "_arm", frame, translate=(8, -2, 0), rotate=(0, 0, 90))
        base = _joint(name + "_cylinder", frame)
        tip = _joint(name + "_rod", arm, translate=(5, 0, 0))
        heading = math.degrees(math.atan2(3.0, 8.0))
        _set(base, "rotateZ", heading)
        _set(tip, "rotateZ", heading + 90)
        setup = Piston.create(base, tip, name=name, aimAxis="x", upAxis="y", minimum=6.5, maximum=11.0)
        _output(name + "_cylinderOut", frame, str(setup.container) + ".baseMatrix", ((5, 0, 0),))
        _output(name + "_rodOut", arm, str(setup.container) + ".tipMatrix", ((4, 0, 0),))
        return setup, arm

    @classmethod
    def _bowString(cls, name, root):
        """弓の上下の先端とノック。ノックを+Z方向へ引くと、弦(緑)がノックへ向かって伸び、drawWeightが増える。"""
        from .setups import BowString

        bow = _transform(name + "_bow", root, translate=(0, 10, 0))
        top = _joint(name + "_top", bow, translate=(0, 6, -1))
        bottom = _joint(name + "_bottom", bow, translate=(0, -6, -1))
        nock = _locator(name + "_nock", bow, translate=(0, 0, 1))
        setup = BowString.create(top, bottom, nock, name=name, aimAxis="x", upAxis="y", maxDraw=6.0)
        for role in ("top", "bottom"):
            string = _output(name + "_" + role + "StringOut", bow, str(setup.container) + "." + role + "Matrix")
            end = _tip(string, name + "_" + role + "StringEnd", (1, 0, 0))
            _connect(str(setup.container) + "." + role + "Length", end + ".translateX")
        return setup, nock

    @classmethod
    def _waveChain(cls, name, root):
        """尻尾の6関節。containerのphaseを変えると波(緑)が根元から先へ進む。"""
        from .setups import WaveChain

        hip = _transform(name + "_hip", root, translate=(0, 5, 0))
        joints, parent = [], hip
        for index in range(6):
            joint = _joint("{}_tail{}".format(name, index), parent, translate=(1.5 if index else 0, 0, 0))
            joints.append(joint)
            parent = joint
        setup = WaveChain.create(joints, name=name, axis="z", amplitude=20.0, wavelength=5.0)
        parent = hip
        for index in range(len(joints)):
            tips = ((1.5, 0, 0),) if index == len(joints) - 1 else ()
            parent = _output("{}_tail{}Out".format(name, index), parent,
                             "{}.matrix{}".format(setup.container, index), tips)
        return setup, str(setup.container)

    @classmethod
    def _waveFloat(cls, name, root):
        """水面に浮かぶ船のコントロール。再生すると船(緑)が2つの波に乗って上下・前後に揺れて傾く。
        コントロールを水平に動かすと、その場所の波に乗る。"""
        from .setups import WaveFloat

        control = _locator(name + "_boatCtrl", root)
        setup = WaveFloat.create(control, name=name, count=2, connectTime=True)
        for index, values in enumerate(((0.6, 12.0, 0.0, 0.5, 0.2), (0.3, 7.0, 40.0, 0.4, 0.15))):
            for attr, value in zip(("amplitude", "wavelength", "direction", "steepness", "speed"), values):
                setup.container.getPlug(attr + str(index)).set(value, uiUnits=True)
        _output(name + "_boatOut", root, str(setup.container) + ".matrix", ((3, 0, 0), (0, 2, 0), (-3, 0, 0)))
        return setup, control

    @classmethod
    def _wheelRoll(cls, name, root):
        """車体と車輪。車体をZ方向へ動かすと、車輪(緑)が移動量に合わせて回る。"""
        from .setups import WheelRoll

        vehicle = _transform(name + "_vehicle", root)
        wheel = _joint(name + "_wheel", vehicle, translate=(0, 1, 0))
        setup = WheelRoll.create(vehicle, wheel, 1.0, name=name, forwardAxis="z", spinAxis="x")
        _output(name + "_wheelOut", vehicle, str(setup.container) + ".matrix", ((0, 1, 0), (0, -1, 0)))
        return setup, vehicle

    @classmethod
    def _rockerRoll(cls, name, root):
        """半径4の円弧の脚(揺り椅子の脚、jointの先が円弧の点)と、それを床の上で転がした出力(緑)。
        containerの ``roll`` を変えると、接地点が円弧の上を移り、底が滑らずに前後へ転がる。"""
        from .setups import RockerRoll

        radius = 4.0
        arc = [(0.0, radius - radius * math.cos(math.radians(angle)), radius * math.sin(math.radians(angle)))
               for angle in (-50, -25, 25, 50)]
        rocker = _joint(name + "_rocker", root)
        for index, point in enumerate(arc):
            _tip(rocker, "{}_rockerTip{}".format(name, index), point)
        _tip(rocker, name + "_rockerSeat", (0.0, radius, 0.0))
        setup = RockerRoll.create(rocker, radius, name=name)
        _output(name + "_rockerOut", root, str(setup.container) + ".matrix", arc + [(0.0, radius, 0.0)])
        return setup, str(setup.container)

    @classmethod
    def _boxRoll(cls, name, root):
        """一辺4の箱(jointの先が断面の正方形の4つの角と上の面の中心)と、それを床の上で転がした出力(緑)。
        containerの ``roll`` を変えると、前の下の縁を支点に箱が傾き、90度ごとに支点が次の縁へ移って転がる。"""
        from .setups import BoxRoll

        size = 4.0
        half = size / 2.0
        corners = [(0.0, 0.0, -half), (0.0, 0.0, half), (0.0, size, half), (0.0, size, -half)]
        box = _joint(name + "_box", root)
        for index, point in enumerate(corners):
            _tip(box, "{}_boxCorner{}".format(name, index), point)
        setup = BoxRoll.create(box, size, name=name)
        _output(name + "_boxOut", root, str(setup.container) + ".matrix", corners + [(0.0, size, 0.0)])
        return setup, str(setup.container)

    @classmethod
    def _outlineBank(cls, name, root):
        """一辺4の正方形の底の輪郭(曲線)と、傾けるコントロール(locator)、傾いた箱の出力(緑)。
        コントロールの ``rotateX``・``rotateZ`` を回すと、傾けた側の縁(輪郭の上の点)を支点に箱が傾く。"""
        from .setups import ControlShape, OutlineBank

        half, height = 2.0, 3.0
        corners = [(half, 0.0, half), (half, 0.0, -half), (-half, 0.0, -half), (-half, 0.0, half)]
        outline = _transform(name + "_outline", root)
        ControlShape.replaceCurves(outline, corners + corners[:1], [0, 1, 2, 3, 4], degree=1, name=name + "_outline")
        control = _locator(name + "_ctrl", root)
        setup = OutlineBank.create(control, outline, name=name)
        _output(name + "_boxOut", root, str(setup.container) + ".matrix",
                corners + [(x, height, z) for x, _, z in corners])
        return setup, control

    @classmethod
    def _crankSlider(cls, name, root):
        """エンジンのクランク(半径2、Z回りに回すjoint)とピストン。クランクの ``rotateZ`` を回すと、
        長さ6のロッド(緑)がピンに付いたままピストンへ向き、ピストン(緑)がY軸に沿って上下する。"""
        from .setups import CrankSlider

        radius, length, start = 2.0, 6.0, 30.0
        height = radius * math.cos(math.radians(start)) + math.sqrt(
            length * length - (radius * math.sin(math.radians(start))) ** 2)
        engine = _transform(name + "_engine", root)
        crank = _joint(name + "_crank", engine, rotate=(0, 0, start))
        pin = _tip(crank, name + "_crankPin", (0.0, radius, 0.0))
        piston = _joint(name + "_piston", engine, translate=(0.0, height, 0.0))
        _tip(piston, name + "_pistonHead", (0.0, 1.5, 0.0))
        setup = CrankSlider.create(pin, piston, name=name, axis="y")
        _output(name + "_rodOut", root, str(setup.container) + ".rodMatrix", ((length, 0.0, 0.0),))
        _output(name + "_pistonOut", root, str(setup.container) + ".pistonMatrix", ((0.0, 1.5, 0.0),))
        return setup, crank

    @classmethod
    def _fourBarLinkage(cls, name, root):
        """四節リンク(クランク2・支点の間6・カプラー5・ロッカー4)。クランクの ``rotateZ`` を回すと、
        カプラー(緑)がピンに付いたまま関節へ向き、ロッカー(緑)が右の支点を中心に往復する。"""
        from .setups import FourBarLinkage

        crank_length, ground, coupler, rocker_length, start = 2.0, 6.0, 5.0, 4.0, 60.0
        angle = math.radians(start)
        bx, by = crank_length * math.cos(angle), crank_length * math.sin(angle)
        joint = FourBarLinkage.jointPosition((bx, by, 0.0), (ground, 0.0, 0.0), coupler, rocker_length,
                                             (0.0, 0.0, 1.0))[0]
        base = _transform(name + "_base", root)
        crank = _joint(name + "_crank", base, rotate=(0, 0, start))
        pin = _tip(crank, name + "_crankPin", (crank_length, 0.0, 0.0))
        rocker = _joint(name + "_rocker", base, translate=(ground, 0.0, 0.0))
        end = _tip(rocker, name + "_rockerEnd", (joint[0] - ground, joint[1], 0.0))
        setup = FourBarLinkage.create(pin, rocker, end, name=name)
        _output(name + "_couplerOut", root, str(setup.container) + ".couplerMatrix", ((coupler, 0.0, 0.0),))
        _output(name + "_rockerOut", root, str(setup.container) + ".rockerMatrix",
                ((joint[0] - ground, joint[1], 0.0),))
        return setup, crank

    @classmethod
    def _scissorLift(cls, name, root):
        """3段のシザーリフト(腕の長さ6)。containerの ``height`` を変えると、X字の腕(緑、先の子jointが腕の
        反対の端)が真ん中で交わったまま開閉し、台(緑、上)が上下し、右の滑る足(緑)が左右へ動く。"""
        from .setups import ScissorLift

        length, stages = 6.0, 3
        base = _transform(name + "_base", root)
        setup = ScissorLift.create(base, length, stages, height=6.0, name=name)
        owner = str(setup.container)
        for index in range(stages):
            for side in "AB":
                _output("{}_arm{}{}Out".format(name, index, side), root,
                        "{}.arm{}{}Matrix".format(owner, index, side), ((length, 0.0, 0.0),))
        _output(name + "_platformOut", root, owner + ".platformMatrix", ((6.0, 0.0, 0.0),))
        for role in ("baseSlider", "topSlider"):
            _output("{}_{}Out".format(name, role), root, "{}.{}Matrix".format(owner, role), ((0.0, 0.8, 0.0),))
        return setup, setup.container

    @classmethod
    def _cableSag(cls, name, root):
        """2本の柱の先の留め具(locator)の間に垂れるケーブルの9点(緑)。右の留め具を動かすと、
        近づけるほど深く垂れ、長さ(containerの ``length``、既定は作成時の距離の1.2倍)以上離すと一直線に張る。"""
        from .setups import CableSag

        posts = []
        for side, x in (("left", -4.0), ("right", 4.0)):
            post = _joint("{}_{}Post".format(name, side), root, translate=(x, 0.0, 0.0))
            _tip(post, "{}_{}PostTop".format(name, side), (0.0, 6.0, 0.0))
            posts.append(_locator("{}_{}Hook".format(name, side), root, translate=(x, 6.0, 0.0)))
        setup = CableSag.create(posts[0], posts[1], 9, name=name, length=9.6)
        for index in range(9):
            _output("{}_cable{}Out".format(name, index), root, "{}.matrix{}".format(setup.container, index),
                    ((0.5, 0.0, 0.0),))
        return setup, posts[1]

    @classmethod
    def _treadBelt(cls, name, root):
        """車体の下の閉じた曲線(履帯の通り道)と、その上を巡回する16枚の板(緑)。
        車体を ``translateZ`` で前へ動かすと、地面に付いた下側の板がその場に止まるように履帯が回る。
        containerの ``phase`` で全体をずらせる。"""
        from .setups import TreadBelt

        vehicle = _transform(name + "_vehicle", root)
        path = _transform(name + "_path", vehicle, translate=(0, 1.2, 0))
        # 半径1.2の円を、前後(Z)へ3倍に伸ばした長円。法線+Xで、曲線の向きが下側で後ろ(-Z)へ進む向きになる。
        _set(path, "scale", (1.0, 1.0, 3.0))
        circle = mlib.createNode("makeNurbCircle", name=name + "_pathCircle", skipSelect=True)
        circle.getPlug("normal").set((1.0, 0.0, 0.0))
        circle.getPlug("radius").set(1.2)
        circle.getPlug("sections").set(16)
        shape = mlib.createNode("nurbsCurve", name=name + "_pathShape", parent=path, skipSelect=True)
        circle.getPlug("outputCurve").connectTo(shape.getPlug("create"))
        setup = TreadBelt.create(path, 16, name=name, normal=(1.0, 0.0, 0.0), driver=vehicle + ".translateZ")
        for index in range(16):
            _output("{}_plate{}Out".format(name, index), root, "{}.matrix{}".format(setup.container, index),
                    ((0.25, 0, 0), (0, 0, 0.8), (0, 0, -0.8)))
        return setup, vehicle

    @classmethod
    def _gearTrain(cls, name, root):
        """駆動側の歯車(joint、十字の先が歯車の半径)と、かみ合う・同じ軸の3つの歯車(緑)。
        駆動側を ``rotateZ`` で回すと、歯数の比(24:12、同じ軸、20:10)で各歯車が逆向き・同じ向きに回る。
        containerの ``teeth0`` 〜 ``teeth3`` で歯数、 ``phase1`` 〜 ``phase3`` で歯の合わせを変えられる。"""
        from .setups import GearTrain

        items = (("driver", (0, 10, 0), 2.4), ("gear1", (3.6, 10, 0), 1.2), ("gear2", (3.6, 10, 1), 2.0),
                 ("gear3", (6.6, 10, 1), 1.0))
        gears = []
        for role, position, radius in items:
            gear = _joint("{}_{}".format(name, role), root, translate=position)
            for index, tip in enumerate(((radius, 0, 0), (0, radius, 0), (-radius, 0, 0), (0, -radius, 0))):
                _tip(gear, "{}_{}Tip{}".format(name, role, index), tip)
            gears.append(gear)
        for gear in gears[1:]:
            _color(gear)
        setup = GearTrain.create(gears[0], gears[1:], (24, 12, 20, 10), name=name, axis="z",
                                 links=("mesh", "shaft", "mesh"))
        return setup, gears[0]

    @classmethod
    def _ackermannSteering(cls, name, root):
        """車体(前+Z)の4つの車輪(joint、十字の先が車輪の半径)と、ハンドル(joint)。前輪は緑。
        ハンドルを ``rotateZ`` で回すと(-1/8の比、運転席から見て左回りで左へ)、左右の前輪が
        アッカーマンの幾何で内輪を大きく切る。containerの ``ackermann`` を0にすると平行に切れる。"""
        from .setups import AckermannSteering

        body = _transform(name + "_body", root, translate=(0, 0.6, 0))
        wheels = []
        for role, position in (("frontLeft", (2, 0, 6)), ("frontRight", (-2, 0, 6)), ("rearLeft", (2, 0, 0)),
                               ("rearRight", (-2, 0, 0))):
            wheel = _joint("{}_{}".format(name, role), body, translate=position)
            for index, tip in enumerate(((0, 0.6, 0), (0, 0, 0.6), (0, -0.6, 0), (0, 0, -0.6), (0.3, 0, 0))):
                _tip(wheel, "{}_{}Tip{}".format(name, role, index), tip)
            wheels.append(wheel)
        for wheel in wheels[:2]:
            _color(wheel)
        handle = _joint(name + "_handle", body, translate=(0.6, 1.4, 3.6))
        for index, tip in enumerate(((0.5, 0, 0), (0, 0.5, 0), (-0.5, 0, 0), (0, -0.5, 0))):
            _tip(handle, "{}_handleTip{}".format(name, index), tip)
        setup = AckermannSteering.create(wheels[0], wheels[1], 6.0, name=name, axis="y",
                                         driver=handle + ".rotateZ", driverRatio=-0.125)
        return setup, handle

    @classmethod
    def _rotationMinimizingFrames(cls, name, root):
        """5つの点。点を動かすと、ねじれを抑えた向き(緑)が点列に沿って付く。"""
        from .setups import RotationMinimizingFrames

        points = [(0, 0, 0), (2, 1, 0), (4, 1, 1), (6, 0, 2), (8, -1, 2)]
        nodes = []
        for index, point in enumerate(points):
            nodes.append(_locator("{}_point{}_loc".format(name, index), root, translate=point))
        setup = RotationMinimizingFrames.create(nodes, name=name, upAxis="z", keepOffset=False)
        for index in range(len(nodes)):
            _output("{}_frame{}Out".format(name, index), root, "{}.matrix{}".format(setup.container, index),
                    ((0.8, 0, 0), (0, 0, 0.8)))
        return setup, nodes[2]

    @classmethod
    def _rotationMinimizingFramesCurve(cls, name, root):
        """曲線。曲線のCVを動かすと、曲線の接線に沿ったねじれを抑えた向き(緑)が付く。"""
        from .setups import RotationMinimizingFrames

        from .setups import ControlShape

        curve = _transform(name + "_crv", root)
        ControlShape.replaceCurves(curve, [(0, 0, 0), (2, 2, 0), (4, 2, 2), (6, 0, 3), (8, -2, 2), (10, 0, 0)],
                                   [0, 0, 0, 1, 2, 3, 3, 3], degree=3, name=name + "_crv")
        setup = RotationMinimizingFrames.fromCurve(curve, 6, name=name, upVector=(0, 0, 1))
        for index in range(6):
            _output("{}_frame{}Out".format(name, index), root, "{}.matrix{}".format(setup.container, index),
                    ((0.8, 0, 0), (0, 0, 0.8)))
        return setup, curve

    @classmethod
    def _ribbon(cls, name, root):
        """5つのコントロール。コントロールを動かす・回すと、帯(テンプレート表示)とその上の7つの向き(緑)が付いてくる。"""
        from .setups import Ribbon

        controls = []
        for index in range(5):
            controls.append(_locator("{}_ctrl{}".format(name, index), root, translate=(index * 3.0, 10, 0)))
        setup = Ribbon.create(controls, count=7, name=name, width=1.5, sideAxis="z")
        for index in range(7):
            _output("{}_ribbon{}Out".format(name, index), root, "{}.matrix{}".format(setup.container, index),
                    ((0.8, 0, 0), (0, 0.8, 0)))
        # 帯のカーブとサーフェスもサンプルのまとめの下へ置く(inheritsTransformを切ってあるので形は変わらない)。
        mlib.nodes.Node(setup.group).setParent(root)
        return setup, controls[2]

    @classmethod
    def _chainNet(cls, name, root):
        """ひれの両端の親チェーン(5節のjoint)と、その間の3本の子チェーン(緑)。親チェーンAの節のrotateZを
        回すと、子チェーンが containerの bias0〜bias2 の割合(Bの動きを使う割合)で付いてくる。
        子チェーンの節はそのまま手付けで回せる。"""
        from .setups import ChainNet

        body = _transform(name + "_body", root, translate=(0, 5, 0))
        chains = {}
        for role, z in (("masterA", -3.0), ("slave0", -1.5), ("slave1", 0.0), ("slave2", 1.5), ("masterB", 3.0)):
            joints, parent = [], body
            for index in range(5):
                joint = _joint("{}_{}_{}".format(name, role, index), parent,
                               translate=(1.5 if index else 0, 0, 0 if index else z))
                if role.startswith("slave"):
                    _color(joint)
                joints.append(joint)
                parent = joint
            chains[role] = [_longName(joint) for joint in joints]
        slaves = [chains["slave" + str(index)] for index in range(3)]
        setup = ChainNet.create(chains["masterA"], chains["masterB"], slaves, name=name, connect=True)
        return setup, chains["masterA"][1]

    @classmethod
    def _leafJoints(cls, name, root):
        """肩・肘・手首・手の先の腕(segmentScaleCompensate付きjoint、肘を太く短くつぶした状態)と、書き出し用の
        枝のjoint・葉のjoint(緑)。肘の scale を変えると肘の葉(緑)だけが太り、枝と前腕より先の葉は scale 1 のまま
        付いてくる。"""
        from .setups import LeafJoints

        arm = _chain(name, root, (("shoulder", (0, 8, 0)), ("elbow", (3.5, 8, -0.3)),
                                  ("wrist", (6.5, 8, 0)), ("hand", (8, 8, 0))))
        for parent, child in zip(arm, arm[1:]):
            # jointツールで作る骨と同じく、親のscaleを inverseScale へ繋いで segmentScaleCompensate を効かせる
            # (mlib.createNode でjointの下へ作った場合は接続済みで、同じ接続なら変更しない)。
            mlib.nodes.Node(child).connectInverseScale(parent)
        _set(arm[1], "scale", (0.8, 1.6, 1.6))
        export = _transform(name + "_export", root)
        setup = LeafJoints.create(arm, name=name, parent=export)
        branches, leaves = setup.getJoints()
        for joint in branches + leaves:
            _color(str(joint))
            _set(str(joint), "radius", 0.6)
        return setup, arm[1]

    @classmethod
    def _bodyProportion(cls, name, root):
        """胸から左右の腕、腰から左右の脚の骨格(標準の体格)。containerの ``armLength`` ・ ``shoulderWidth`` ・
        ``legLength`` ・ ``armThickness`` を変えると、体格調整用の骨(緑)の移動・スケールが生成時の体格から変わる。
        値は -1〜1(太さは -1〜2)の範囲でclampし、負の側は別の量(短く・細く)を持つ。"""
        from .setups import BodyProportion

        body = _transform(name + "_body", root)
        hips, chest = _chain(name, body, (("hips", (0, 9, 0)), ("chest", (0, 13, 0))))
        _tip(chest, name + "_head", (0, 2.5, 0))
        targets = {"armLength": {}, "shoulderWidth": {}, "legLength": {}, "armThickness": {}}
        for side, sign in (("L", 1), ("R", -1)):
            shoulder, elbow, wrist = _chain(name, chest, (
                ("shoulder" + side, (1.5 * sign, 13.5, 0)), ("elbow" + side, (4.5 * sign, 13.5, -0.3)),
                ("wrist" + side, (7.5 * sign, 13.5, 0))))
            _tip(wrist, "{}_hand{}".format(name, side), (1.2 * sign, 0, 0))
            hip, knee, ankle = _chain(name, hips, (
                ("hip" + side, (1.0 * sign, 9, 0)), ("knee" + side, (1.0 * sign, 5, 0.3)),
                ("ankle" + side, (1.0 * sign, 1, 0))))
            _tip(ankle, "{}_toe{}".format(name, side), (0, -0.6, 1.2))
            targets["armLength"][elbow] = {"translate": (0.9 * sign, 0, 0), "translateNegative": (-0.6 * sign, 0, 0)}
            targets["armLength"][wrist] = {"translate": (0.9 * sign, 0, 0), "translateNegative": (-0.6 * sign, 0, 0)}
            targets["shoulderWidth"][shoulder] = {"translate": (0.8 * sign, 0, 0)}
            targets["legLength"][knee] = {"translate": (0, -0.8, 0)}
            targets["legLength"][ankle] = {"translate": (0, -0.8, 0)}
            targets["armThickness"][shoulder] = {"scale": (0, 0.4, 0.4), "scaleNegative": (0, -0.3, -0.3)}
            for joint in (shoulder, elbow, wrist, knee, ankle):
                _color(joint)
        parameters = [{"name": key, "targets": value} for key, value in targets.items()]
        parameters[-1]["maximum"] = 2.0
        setup = BodyProportion.create(parameters, name=name)
        return setup, str(setup.container)

    @classmethod
    def _metaSpread(cls, name, root):
        """手のひらの4本の中手骨。小指側(最後)のjointを回すと、間の2本(緑)が割合に応じて付いてくる。"""
        from .setups import MetaSpread

        hand = _transform(name + "_hand", root, translate=(0, 10, 0))
        metas = []
        for index in range(4):
            meta = _joint("{}_meta{}".format(name, index), hand, translate=(0.5, 0, 1.5 - index),
                          rotate=(0, 6 * index - 9, 0))
            _tip(meta, "{}_meta{}Tip".format(name, index), (3, 0, 0))
            metas.append(meta)
        setup = MetaSpread.create(metas[0], metas[3], metas[1:3], name=name)
        for index in range(2):
            _output("{}_meta{}Out".format(name, index + 1), hand, "{}.matrix{}".format(setup.container, index),
                    ((3, 0, 0),))
        return setup, metas[3]

    @classmethod
    def _neckHeadSplit(cls, name, root):
        """胸の上の3つの首の関節と頭(灰色のjoint)、頭の前の円のコントロール。コントロールを回すと、
        回転が首の3つの関節へ割合(containerの ``weight0`` 〜 ``weight2``、既定は各1/4)で分かれて首(緑)が
        しなり、頭(緑)はコントロールと同じ向きになる。"""
        from .setups import ControlShape, NeckHeadSplit

        chest = _transform(name + "_chest", root, translate=(0, 10, 0))
        joints, parent = [], chest
        for index, role in enumerate(("neck0", "neck1", "neck2", "head")):
            joint = _joint("{}_{}".format(name, role), parent, translate=(0, 1.2 if index else 0.5, 0.15))
            joints.append(joint)
            parent = joint
        _tip(joints[-1], name + "_headTip", (0, 2.5, 0))
        control = _transform(name + "_ctrl", root, translate=(0, 14.2, 0.45))
        circle = [(1.5 * x, 0, 1.5 * z) for x, z in ((0, 1), (1, 0), (0, -1), (-1, 0), (0, 1))]
        ControlShape.replaceCurves(control, circle, [0, 1, 2, 3, 4], degree=1, name=name + "_ctrl")
        setup = NeckHeadSplit.create(chest, joints, control, name=name)
        for index, role in enumerate(("neck0", "neck1", "neck2", "head")):
            tip = (0, 2.5, 0) if role == "head" else (0, 1.2, 0.15)
            _output("{}_{}Out".format(name, role), root, "{}.matrix{}".format(setup.container, index), (tip,))
        return setup, control

    @classmethod
    def _footRoll(cls, name, root):
        """+Zを向いた足。containerのrollを正にすると母指球→つま先、負にするとかかとを支点に足(緑)が転がり、
        bankで内外の縁を支点に傾く。"""
        from .setups import FootRoll

        control = _locator(name + "_footCtrl", root)
        pivots = {
            role: _locator("{}_{}Pivot".format(name, role), control, translate=position)
            for role, position in (
                ("toe", (0, 0, 7)), ("heel", (0, 0, -1.5)), ("inner", (1.5, 0, 3)), ("outer", (-1.5, 0, 3)),
            )
        }
        ankle = _joint(name + "_ankle", root, translate=(0, 4, 0))
        ball = _joint(name + "_ball", ankle, translate=(0, -3.2, 4))
        _tip(ball, name + "_ballTip", (0, -0.8, 3))
        setup = FootRoll.create(
            control, ankle, ball, pivots["toe"], pivots["heel"], pivots["inner"], pivots["outer"],
            name=name, rollAxis="x", bankAxis="z", breakAngle=30.0,
        )
        _output(name + "_ankleOut", root, str(setup.container) + ".ankleMatrix", ((0, -3.2, 4),))
        _output(name + "_ballOut", root, str(setup.container) + ".ballMatrix", ((0, -0.8, 3),))
        return setup, setup.container

    @classmethod
    def _muscleBulge(cls, name, root):
        """上腕と肘。肘のrotateZを曲げると、上腕の中央の補助骨(緑)が60度から膨らみ始め、140度で最大になる。"""
        from .setups import MuscleBulge

        shoulder = _transform(name + "_shoulder", root, translate=(0, 10, 0))
        upper = _joint(name + "_upperArm", shoulder)
        elbow = _joint(name + "_elbow", upper, translate=(5, 0, 0))
        _tip(elbow, name + "_elbowTip", (4, 0, 0))
        setup = MuscleBulge.create(upper, elbow, name=name, axis="x", pushAxis="y", startAngle=60.0,
                                   fullAngle=140.0, bulge=0.6, push=0.6)
        _output(name + "_bulgeOut", upper, str(setup.container) + ".matrix", ((0, 0.8, 0), (0, 0, 0.8)))
        return setup, elbow

    @classmethod
    def _pumpUp(cls, name, root):
        """上腕と肘と、肘の曲げで膨らむ補助骨(MuscleBulge、既定の色)。pumpのlocatorを上へ動かすと、
        補助骨の膨らみを増幅した骨(緑)が太くなる。肘のrotateZを曲げた状態で動かすと膨らみの変化も増える。"""
        from .setups import MuscleBulge, PumpUp

        shoulder = _transform(name + "_shoulder", root, translate=(0, 10, 0))
        upper = _joint(name + "_upperArm", shoulder)
        elbow = _joint(name + "_elbow", upper, translate=(5, 0, 0))
        _tip(elbow, name + "_elbowTip", (4, 0, 0))
        bulge = MuscleBulge.create(upper, elbow, name=name + "_bulgeGraph", axis="x", pushAxis="y",
                                   startAngle=60.0, fullAngle=140.0, bulge=0.6, push=0.6)
        helper = _joint(name + "_bulge", upper)
        _set(helper, "radius", 0.6)
        _connect(str(bulge.container) + ".matrix", helper + ".offsetParentMatrix")
        for index, translate in enumerate(((0, 0.8, 0), (0, 0, 0.8))):
            _tip(helper, "{}_bulgeTip{}".format(name, index), translate)
        # pumpのlocatorは、translateYが0から始まるよう上腕の上の空のtransformの下に置く。
        space = _transform(name + "_pumpSpace", root, translate=(2.5, 13, 0))
        control = _locator(name + "_pumpCtrl", space)
        setup = PumpUp.create([helper], name=name, driver=control + ".translateY", gains=(1.5,),
                              scaleOffsets=((0.0, 0.4, 0.4),))
        _output(name + "_pumpOut", upper, str(setup.container) + ".matrix0", ((0, 0.8, 0), (0, 0, 0.8)))
        return setup, control

    @classmethod
    def _groundTilt(cls, name, root):
        """4本の足の接地点(locator)と胴体。左前足を上下すると、胴体(緑)が足の面に合わせて傾き上下する。"""
        from .setups import GroundTilt

        body = _locator(name + "_bodyCtrl", root, translate=(0, 5, 0))
        feet = [
            _locator("{}_{}Foot".format(name, role), root, translate=position)
            for role, position in (
                ("frontLeft", (4, 0, 1.5)), ("frontRight", (4, 0, -1.5)),
                ("backLeft", (-4, 0, 1.5)), ("backRight", (-4, 0, -1.5)),
            )
        ]
        setup = GroundTilt.create(body, *feet, name=name)
        _output(name + "_bodyOut", root, str(setup.container) + ".matrix", ((4, 0, 0), (0, 0, 1.5)))
        return setup, feet[0]

    @classmethod
    def _centerOfMass(cls, name, root):
        """骨盤・背骨・胸・頭・左右の腕(Tポーズ)と脚の棒人間(灰色のjoint)。体節の質量の割合(一般的な人体の表)から
        求めた全身の重心(緑、 ``_comOut``)と、その床への投影(緑、 ``_floorOut``)を作る。背骨のjointを ``rotateX``
        で前へ倒すと重心が前へ移り、containerの ``balance`` (両足首の中点からの床の上の距離)が増える。"""
        from .setups import CenterOfMass

        pelvis = _joint(name + "_pelvis", root, translate=(0, 9, 0))
        spine = _joint(name + "_spine", pelvis, translate=(0, 0.5, 0))
        chest = _joint(name + "_chest", spine, translate=(0, 3.5, 0))
        head = _joint(name + "_head", chest, translate=(0, 1.6, 0))
        _tip(head, name + "_headTip", (0, 1.4, 0))
        table = CenterOfMass.DEMPSTER
        segments = [
            dict(start=pelvis, end=chest, mass=table["trunk"][0], ratio=table["trunk"][1]),
            dict(start=chest, end=head, mass=table["headNeck"][0], ratio=table["headNeck"][1]),
        ]
        feet = []
        for side, sign in (("L", 1), ("R", -1)):
            shoulder = _joint("{}_shoulder{}".format(name, side), chest, translate=(1.6 * sign, -0.3, 0))
            elbow = _joint("{}_elbow{}".format(name, side), shoulder, translate=(2.8 * sign, 0, 0))
            wrist = _joint("{}_wrist{}".format(name, side), elbow, translate=(2.6 * sign, 0, 0))
            hand = _tip(wrist, "{}_hand{}".format(name, side), (1.0 * sign, 0, 0))
            hip = _joint("{}_hip{}".format(name, side), pelvis, translate=(0.9 * sign, -0.3, 0))
            knee = _joint("{}_knee{}".format(name, side), hip, translate=(0, -4.2, 0.1))
            ankle = _joint("{}_ankle{}".format(name, side), knee, translate=(0, -4.0, -0.1))
            toe = _tip(ankle, "{}_toe{}".format(name, side), (0, -0.5, 1.6))
            for role, start, end in (("upperArm", shoulder, elbow), ("forearm", elbow, wrist), ("hand", wrist, hand),
                                     ("thigh", hip, knee), ("shank", knee, ankle), ("foot", ankle, toe)):
                segments.append(dict(start=start, end=end, mass=table[role][0], ratio=table[role][1]))
            feet.append(ankle)
        setup = CenterOfMass.create(segments, name=name, support=feet)
        _output(name + "_comOut", root, str(setup.container) + ".centerMatrix")
        _output(name + "_floorOut", root, str(setup.container) + ".groundMatrix")
        return setup, spine

    @classmethod
    def _skirtLegOffset(cls, name, root):
        """腰と左右の脚と、外へ開いた8本のスカートの骨(緑)。左の股関節のrotateXで脚を前へ上げると、
        脚に近い前側の骨が脚から離れる向きへ開き、後ろの骨は動かない。"""
        import math

        from .setups import SkirtLegOffset

        pelvis = _transform(name + "_pelvis", root, translate=(0, 10, 0))
        legs = []
        for side, x in (("L", 1.2), ("R", -1.2)):
            hip, knee, _ = _chain(name, pelvis, (("hip" + side, (x, 9.5, 0)), ("knee" + side, (x, 5, 0.3)),
                                                 ("ankle" + side, (x, 0.5, 0))))
            legs.append((hip, knee))
        skirts = []
        for index in range(8):
            angle = 2 * math.pi * index / 8
            out = (math.sin(angle), math.cos(angle))
            skirt = _joint("{}_skirt{}".format(name, index), pelvis, translate=(2.2 * out[0], 0, 2.2 * out[1]))
            _tip(skirt, "{}_skirt{}Tip".format(name, index), (1.2 * out[0], -4.5, 1.2 * out[1]))
            _color(skirt)
            skirts.append(skirt)
        setup = SkirtLegOffset.create(pelvis, skirts, legs, name=name, connect=True)
        return setup, legs[0][0]

    @classmethod
    def _lipZip(cls, name, root):
        """少し開いた口の上唇・下唇の5組の点(locator)。containerのzipLeft・zipRightを上げると、
        口角に近い組から順に上唇・下唇(緑)が閉じ合わさる。"""
        from .setups import LipZip

        head = _transform(name + "_head", root, translate=(0, 10, 0))
        upper, lower = [], []
        for index in range(5):
            x = index - 2.0
            curve = 0.4 * (1.0 - (x / 2.0) ** 2)
            upper.append(_locator("{}_upper{}".format(name, index), head, translate=(x, 0.3 + curve, curve)))
            lower.append(_locator("{}_lower{}".format(name, index), head, translate=(x, -0.3 - curve, curve)))
        # 右の口角(-X側)から左の口角(+X側)へ並べる。
        setup = LipZip.create(upper, lower, name=name, falloff=0.3)
        for index in range(5):
            for role in ("upper", "lower"):
                _output("{}_{}{}Out".format(name, role, index), root,
                        "{}.{}Matrix{}".format(setup.container, role, index), ((0, 0, 0.4),))
        return setup, setup.container

    @classmethod
    def _squashBox(cls, name, root):
        """高さ4・幅3の箱の基準(locator)。containerのtop・bottom・outer・innerを正にするとその辺が伸び、
        負にすると潰れ、出力(緑、子jointが箱の角)は体積を保つように反対の向きへ細く・太くなる。"""
        from .setups import SquashBox

        control = _locator(name + "_boxCtrl", root, translate=(0, 10, 0))
        setup = SquashBox.create(control, name=name, height=4.0, width=3.0)
        corners = ((1.5, 2, 0), (-1.5, 2, 0), (-1.5, -2, 0), (1.5, -2, 0))
        _output(name + "_boxOut", root, str(setup.container) + ".matrix", corners)
        return setup, setup.container

    @classmethod
    def _planeCollision(cls, name, root):
        """少し傾いた床(locator、ローカルYが法線)と足のコントロール(locator)。コントロールを下げると、
        床から radius + softness の高さで出力(緑)が柔らかく止まり始め、床より下へは沈まない。"""
        from .setups import PlaneCollision

        floor = _locator(name + "_floor", root, translate=(0, 0, 0))
        _set(floor, "rotateZ", 10.0)
        _set(floor, "scale", (6.0, 6.0, 6.0))
        control = _locator(name + "_footCtrl", root, translate=(0, 3, 0))
        setup = PlaneCollision.create(control, floor, name=name, axis="y", softness=1.0, radius=0.5)
        _output(name + "_footOut", root, str(setup.container) + ".matrix", ((0, -0.5, 0),))
        return setup, control

    @classmethod
    def _sphereCollision(cls, name, root):
        """頭を表す球のコライダー(locator)と手のコントロール(locator)。コントロールを球へ近づけると、
        表面から softness の距離で出力(緑)が柔らかく止まり始め、球の中へは入らない。"""
        from .setups import SphereCollision

        head = _locator(name + "_head", root, translate=(0, 6, 0))
        _set(head, "scale", (3.0, 3.0, 3.0))
        control = _locator(name + "_handCtrl", root, translate=(6, 6, 0))
        setup = SphereCollision.create(control, head, name=name, radius=3.0, softness=1.0)
        _output(name + "_handOut", root, str(setup.container) + ".matrix", ((0, 0, 0),))
        return setup, control

    @classmethod
    def _capsuleCollision(cls, name, root):
        """太ももを表すカプセルのコライダー(股関節と膝のlocator)とスカートのコントロール(locator)。
        コントロールを太ももへ近づけると、表面から softness の距離で出力(緑)が柔らかく止まり始め、
        先細りのカプセルの中へは入らない。"""
        from .setups import CapsuleCollision

        hip = _locator(name + "_hip", root, translate=(0, 10, 0))
        knee = _locator(name + "_knee", root, translate=(0, 2, 0))
        control = _locator(name + "_skirtCtrl", root, translate=(6, 6, 0))
        setup = CapsuleCollision.create(control, hip, knee, name=name, startRadius=2.5, endRadius=1.8,
                                        softness=1.0)
        _output(name + "_skirtOut", root, str(setup.container) + ".matrix", ((0, 0, 0),))
        return setup, control

    @classmethod
    def _ellipsoidCollision(cls, name, root):
        """胸を表す楕円体のコライダー(横長・前後に薄い、少し傾けたlocator)と手のコントロール(locator)。
        コントロールを胸へ近づけると、表面から softness の距離で出力(緑)が柔らかく止まり始め、
        楕円体の中へは入らない。"""
        from .setups import EllipsoidCollision

        chest = _locator(name + "_chest", root, translate=(0, 8, 0))
        mlib.getPlug(chest + ".rotateZ").set(15.0)
        control = _locator(name + "_handCtrl", root, translate=(1, 8, 7))
        setup = EllipsoidCollision.create(control, chest, name=name, radiusX=4.0, radiusY=5.0, radiusZ=2.5,
                                          softness=1.0)
        _output(name + "_handOut", root, str(setup.container) + ".matrix", ((0, 0, 0),))
        return setup, control

    @classmethod
    def _boxCollision(cls, name, root):
        """机の天板を表す箱のコライダー(横長で薄い、角を丸めたlocator)と手のコントロール(locator)。
        コントロールを天板へ下ろすと、表面から softness の距離で出力(緑)が柔らかく止まり始め、
        箱の中へは入らない。縁の外へ動かすと丸めた角に沿って回り込む。"""
        from .setups import BoxCollision

        table = _locator(name + "_table", root, translate=(0, 6, 0))
        mlib.getPlug(table + ".rotateY").set(20.0)
        control = _locator(name + "_handCtrl", root, translate=(2, 9, 1))
        setup = BoxCollision.create(control, table, name=name, sizeX=10.0, sizeY=2.0, sizeZ=6.0, rounding=0.5,
                                    softness=1.0)
        _output(name + "_handOut", root, str(setup.container) + ".matrix", ((0, 0, 0),))
        return setup, control

    @classmethod
    def _spaceBlend(cls, name, root):
        """world・胸・手の3つの空間(locator)とコントロール。手の空間を動かすと、worldと手に半分ずつ追従する
        出力(緑)が手の半分だけ付いてくる。containerの weight0〜weight2 で割合を変えられる。"""
        from .setups import SpaceBlend

        spaces = [
            _locator("{}_{}Space".format(name, role), root, translate=position)
            for role, position in (("world", (0, 0, 0)), ("chest", (0, 12, 0)), ("hand", (6, 9, 2)))
        ]
        control = _locator(name + "_ctrl", root, translate=(3, 8, 3))
        setup = SpaceBlend.create(control, spaces, name=name, weights=(1.0, 0.0, 1.0))
        _output(name + "_ctrlOut", root, str(setup.container) + ".matrix", ((1, 0, 0), (0, 1, 0)))
        return setup, spaces[2]

    @classmethod
    def _cameraAngleReader(cls, name, root):
        """顔(頭のjoint、正面は+Z)とカメラ(locator)。頭の前・左・右・上・下・後ろに置いた緑のlocatorの
        大きさが、その方向の重み(containerの weightFront〜weightBack)を表す。カメラを頭の周りに動かすと、
        近い方向の重みへ連続に移る。"""
        from .setups import CameraAngleReader
        from .setups.cameraAngleReader import WEIGHTS

        head = _joint(name + "_head", root, translate=(0, 12, 0))
        _tip(head, name + "_headTip", (0, 2, 0))
        _tip(head, name + "_nose", (0, 0.5, 1.2))
        camera = _locator(name + "_camera", root, translate=(4, 14, 14))
        setup = CameraAngleReader.create(head, camera, name=name)
        places = ((0, 0, 3), (3, 0, 0), (-3, 0, 0), (0, 3, 0), (0, -3, 0), (0, 0, -3))
        for attr, offset in zip(WEIGHTS, places):
            marker = _locator("{}_{}".format(name, attr), root,
                              translate=(offset[0], 12 + offset[1], offset[2]))
            _color(marker)
            for axis in "XYZ":
                _connect(str(setup.container) + "." + attr, marker + ".scale" + axis)
        return setup, camera

    @classmethod
    def _dollyZoom(cls, name, root):
        """被写体(頭の高さのjoint)と、奥へ並ぶ柱のlocator、被写体を正面から見るカメラ。カメラを前後に
        動かすと焦点距離(containerの ``focalLength``)が距離に比例して変わり、カメラから覗くと被写体の
        大きさはそのままで背景の柱の広がりだけが変わる。被写体の面の幅を示す緑のjointの両端が画面の左右の端。"""
        from .setups import DollyZoom

        subject = _joint(name + "_subject", root, translate=(0, 10, 0))
        _tip(subject, name + "_subjectTip", (0, 3, 0))
        for index, (x, z) in enumerate(((-6, -15), (6, -15), (-6, -40), (6, -40), (-6, -80), (6, -80))):
            post = _locator("{}_post{}".format(name, index), root, translate=(x, 10, z))
            _set(post, "scale", (1.0, 8.0, 1.0))
        camera = _transform(name + "_camera", root, translate=(0, 10, 30))
        shape = mlib.createNode("camera", name=name + "_cameraShape", parent=camera, skipSelect=True)
        shape.getPlug("focalLength").set(35.0)
        setup = DollyZoom.create(camera, subject, name=name)
        # 被写体の面の幅(frameWidth)を左右の端の子jointで示す。
        half = setup.container.getPlug("frameWidth").get() / 2.0
        marker = _joint(name + "_frameOut", root, translate=(0, 10, 0))
        _set(marker, "radius", 0.6)
        _color(marker)
        for index, x in enumerate((-half, half)):
            _color(_tip(marker, "{}_frameOutTip{}".format(name, index), (x, 0, 0)))
        return setup, camera

    @classmethod
    def _overShoulderCamera(cls, name, root):
        """向かい合う2人(頭のjointと体のlocator)と、手前の人物の肩越しに奥の人物を写すカメラ。奥の人物の
        頭を動かすとカメラが付いていき、頭は画面の右の三分割の位置(screenX=1/3, screenY=1/3)に写る。
        カメラは2人を結ぶ線の片側(side=1)から動かない。カメラの位置を示す緑のjointを置く。"""
        from .setups import OverShoulderCamera

        heads = []
        for role, z, aim in (("focus", 0.0, 0.0), ("partner", 12.0, 180.0)):
            body = _locator("{}_{}Body".format(name, role), root, translate=(0, 7, z))
            _set(body, "scale", (1.5, 7.0, 1.0))
            head = _joint("{}_{}Head".format(name, role), root, translate=(0, 15, z), rotate=(0, aim, 0))
            _tip(head, "{}_{}Nose".format(name, role), (0, 0, 1.2))
            heads.append(head)
        camera = _transform(name + "_camera", root, translate=(0, 15, 30))
        shape = mlib.createNode("camera", name=name + "_cameraShape", parent=camera, skipSelect=True)
        shape.getPlug("focalLength").set(35.0)
        setup = OverShoulderCamera.create(camera, heads[0], heads[1], name=name, distance=26.0, angle=40.0,
                                          height=3.0, screenX=1.0 / 3.0, screenY=1.0 / 3.0, weight=1.0)
        marker = _joint(name + "_cameraOut", camera)
        _set(marker, "radius", 0.8)
        _color(marker)
        _color(_tip(marker, name + "_cameraOutTip", (0, 0, -2)))
        return setup, heads[0]

    @classmethod
    def _liveMirror(cls, name, root):
        """キャラクターのルート(対称面はルートのYZ面)の左に肩・肘・手首のjoint、右に左の鏡像(Behavior)の
        緑のjoint。左の肩・肘・手首を回すと、右が対称面で鏡に映した姿勢へ付いてくる。ルートを動かす・回すと
        対称面も一緒に動く。右のjointの rotate 等は空いていて、鏡像の上に調整を上乗せできる。"""
        from .setups import LiveMirror

        center = _transform(name + "_root", root)
        plane = _locator(name + "_mirrorPlane", center, translate=(0, 12, 0))
        _set(plane, "scale", (0.05, 6.0, 6.0))
        _set(plane, "template", True)
        left = _joint(name + "_shoulderL", center, translate=(2, 15, 0), rotate=(0, 0, -30))
        elbow = _joint(name + "_elbowL", left, translate=(4, 0, 0), rotate=(0, 20, 0))
        hand = _joint(name + "_handL", elbow, translate=(4, 0, 0))
        _tip(hand, name + "_handLTip", (1.5, 0, 0))
        _tip(hand, name + "_handLThumb", (0.5, 0, 1.0))
        sources = [left, elbow, hand]
        targets, parent = [], center
        for source in sources:
            role = source.rsplit("|", 1)[-1][len(name) + 1:-1]
            joint = _joint("{}_{}R".format(name, role), parent)
            _set(joint, "radius", 0.6)
            _color(joint)
            world = LiveMirror.mirror(mlib.nodes.Node(source).getPlug("worldMatrix")[0].get(),
                                      mlib.nodes.Node(center).getPlug("worldMatrix")[0].get())
            mlib.nodes.Node(joint).setMatrix(world, worldSpace=True)
            targets.append(_longName(joint))
            parent = targets[-1]
        _color(_tip(targets[-1], name + "_handRTip", (-1.5, 0, 0)))
        _color(_tip(targets[-1], name + "_handRThumb", (-0.5, 0, -1.0)))
        # 肩の鏡像をサンプルのcontainer(name)にし、肘・手首は別のcontainerで作る。
        setup = LiveMirror.create(_longName(left), targets[0], name=name, plane=center)
        for role, source, target in (("elbow", elbow, targets[1]), ("hand", hand, targets[2])):
            LiveMirror.create(_longName(source), target, name="{}_{}Mirror".format(name, role), plane=center)
        return setup, _longName(left)

    @classmethod
    def _eyeHighlight(cls, name, root):
        """頭のjointの下の左右の眼球(半径1の球のjoint)と、各眼球の表面のハイライト(緑の小さいjoint)、
        カメラと光のlocator。カメラを動かすと、ハイライトはカメラと光の中間の向きの眼球の表面へ移る。
        眼球を回すと、ハイライトは目と一緒に回らずカメラ・光から見た位置に留まる(follow=1)。
        containerの ``follow`` を0にすると瞳の中心に留まる。左目をサンプルのcontainer(name)、右目を
        ``_rightHighlight`` のcontainerで作る。"""
        from .setups import EyeHighlight

        head = _joint(name + "_head", root, translate=(0, 12, 0))
        _set(head, "radius", 0.3)
        camera = _locator(name + "_camera", root, translate=(6, 15, 16))
        light = _locator(name + "_light", root, translate=(-10, 24, 12))
        _set(light, "scale", (2.0, 2.0, 2.0))
        setup = None
        for side, x in (("left", 1.6), ("right", -1.6)):
            eye = _joint("{}_{}Eye".format(name, side), head, translate=(x, 1.5, 1.0))
            _set(eye, "radius", 1.0)
            _tip(eye, "{}_{}Pupil".format(name, side), (0, 0, 1.0))
            highlight = _joint("{}_{}HighlightOut".format(name, side), eye, translate=(0, 0, 1.05))
            _set(highlight, "radius", 0.15)
            _color(highlight)
            created = EyeHighlight.create(eye, camera, highlight, light=light, weight=1.0,
                                          name=name if setup is None else name + "_rightHighlight")
            if setup is None:
                setup = created
        return setup, camera

    @classmethod
    def _unevenGround(cls, name, root):
        """平らな床(高さ0)で置いた腰と左右の足のlocatorと、足ごとの地面のlocator(左=傾いた段、右=坂)。
        緑の出力(腰・左右の足)は、足が地面の高さと傾きに載り、腰が低い方の足に合わせて下がる。
        左の地面を上下・回転すると、左足(緑)が付いてくる。足のlocatorを動かすと、その位置の地面の高さで載り直す。"""
        from .setups import UnevenGround

        hips = _locator(name + "_hipsCtrl", root, translate=(0, 9, 0))
        left = _locator(name + "_leftFootCtrl", root, translate=(1.5, 0, 0.5))
        right = _locator(name + "_rightFootCtrl", root, translate=(-1.5, 0, -0.5))
        leftGround = _locator(name + "_leftGround", root, translate=(1.5, 1.5, 0))
        _set(leftGround, "rotate", (12.0, 0.0, 8.0))
        rightGround = _locator(name + "_rightGround", root, translate=(-1.5, 0, 0))
        _set(rightGround, "rotate", (0.0, 0.0, -15.0))
        for ground in (leftGround, rightGround):
            _set(ground, "scale", (2.0, 0.3, 2.0))
        setup = UnevenGround.create(hips, left, right, leftGround, rightGround, name=name)
        owner = str(setup.container)
        _output(name + "_hipsOut", root, owner + ".hipsMatrix", ((0, -1.5, 0),))
        _output(name + "_leftFootOut", root, owner + ".leftFootMatrix", ((0, 0, 1.2),))
        _output(name + "_rightFootOut", root, owner + ".rightFootMatrix", ((0, 0, 1.2),))
        return setup, leftGround

    @classmethod
    def _hipSwing(cls, name, root):
        """COG のlocatorの下の腰・背骨の根元・胸のjointと、背骨の根元の位置に置いた振りのコントロール(locator)。
        コントロールを回すと、緑の腰( ``_hipsOut`` )だけがコントロールの位置を支点に振れ、緑の背骨・胸
        ( ``_spineOut`` )は傾かずに元の向きを保つ。containerの ``stabilize`` を0にすると上体も一緒に回り、
        ``swing`` で振りの割合を変えられる。"""
        from .setups import HipSwing

        cog = _locator(name + "_cog", root, translate=(0, 10, 0))
        _set(cog + "|" + name + "_cogShape", "localScale", (3.0, 3.0, 3.0))
        hips = _joint(name + "_hips", cog)
        for side, x in (("L", 1.2), ("R", -1.2)):
            _tip(_tip(hips, "{}_hip{}".format(name, side), (x, -0.8, 0)), "{}_knee{}".format(name, side), (0, -4.0, 0))
        spine = _joint(name + "_spine", hips, translate=(0, 1.0, 0))
        chest = _joint(name + "_chest", spine, translate=(0, 3.0, 0))
        _tip(chest, name + "_neck", (0, 2.0, 0))
        control = _locator(name + "_swingCtrl", cog, translate=(0, 1.0, 0))
        _set(control + "|" + name + "_swingCtrlShape", "localScale", (1.5, 1.5, 1.5))
        setup = HipSwing.create(hips, spine, control, name=name)
        owner = str(setup.container)
        hipsOut = _output(name + "_hipsOut", root, owner + ".hipsMatrix")
        for side, x in (("L", 1.2), ("R", -1.2)):
            _color(_tip(_tip(hipsOut, "{}_hipOut{}".format(name, side), (x, -0.8, 0)),
                        "{}_kneeOut{}".format(name, side), (0, -4.0, 0)))
        spineOut = _output(name + "_spineOut", root, owner + ".spineMatrix")
        chestOut = _joint(name + "_chestOut", spineOut, translate=(0, 3.0, 0))
        _color(chestOut)
        _color(_tip(chestOut, name + "_neckOut", (0, 2.0, 0)))
        return setup, control

    @classmethod
    def _uiSlider(cls, name, root):
        """顔のUIパネルの2次元スライダー(枠はテンプレート表示の正方形)。枠の中でコントロールを動かすと、
        周りの8つの緑のlocatorの大きさが、その方向・角の重み(containerの right〜downLeft)を表す。
        コントロールは枠の外へ出ない。"""
        from .setups import ControlShape, UiSlider
        from .setups.uiSlider import OUTPUTS

        size = 2.0
        border = _transform(name + "_border", root, translate=(0, 10, 0))
        corners = [(-size, -size, 0), (size, -size, 0), (size, size, 0), (-size, size, 0), (-size, -size, 0)]
        ControlShape.replaceCurves(border, corners, [0, 1, 2, 3, 4], degree=1, name=name + "_border")
        _set(border, "template", True)
        control = _transform(name + "_ctrl", border)
        handle = [(x * 0.4, y * 0.4, 0) for x, y, _ in corners]
        ControlShape.replaceCurves(control, handle, [0, 1, 2, 3, 4], degree=1, name=name + "_ctrl")
        setup = UiSlider.create(control, name=name, size=size)
        places = {"right": (1, 0), "left": (-1, 0), "up": (0, 1), "down": (0, -1),
                  "upRight": (1, 1), "upLeft": (-1, 1), "downRight": (1, -1), "downLeft": (-1, -1)}
        for attr in OUTPUTS[2:]:
            x, y = places[attr]
            marker = _locator("{}_{}".format(name, attr), root, translate=(x * 3.2, 10 + y * 3.2, 0))
            _color(marker)
            for axis in "XYZ":
                _connect(str(setup.container) + "." + attr, marker + ".scale" + axis)
        return setup, control

    @classmethod
    def _comboWeight(cls, name, root):
        """左右の口角のコントロール(locator、translateY が 0〜1 のウェイト)と、口の真ん中の補助骨(緑のjoint)。
        真ん中の骨は左右それぞれのウェイトで半分ずつ上がるので、両方を上げると口角と同じ高さまで上がりすぎる。
        組み合わせのウェイト(containerの ``both``)で戻す分を足し、両方を上げると真ん中は元の高さへ戻って
        口角だけが上がる(赤のlocatorは戻さない場合の位置)。上の2つの緑のlocatorの大きさが ``both`` と、
        左のウェイトが0.5で最大になる ``leftHalf`` を表す。作成時は右の口角を上げてあり、左のコントロールを上げると補正が効く。"""
        from .setups import ComboWeight

        lift = 1.0
        controls = {}
        for side, x in (("left", 3.0), ("right", -3.0)):
            # コントロールの translateY を 0 から測るため、口の高さへ上げた親の下に置く。
            offset = _transform("{}_{}CtrlOffset".format(name, side), root, translate=(x, 6.0, 0))
            controls[side] = _locator("{}_{}Ctrl".format(name, side), offset)
        setup = ComboWeight.create(
            {"left": controls["left"] + ".translateY", "right": controls["right"] + ".translateY"},
            {"both": ["left", "right"]}, {"leftHalf": ("left", 0.5)}, name=name)
        owner = str(setup.container)
        centers = {}
        for role, fix in (("center", True), ("plain", False)):
            # 真ん中の高さ = 6 + lift/2 * (left + right) - lift * both(赤の plain は補正なし)。
            height = mlib.createNode("blendWeighted", name="{}_{}Height".format(name, role), skipSelect=True)
            height.getPlug("input")[0].set(6.0)
            height.getPlug("weight")[0].set(1.0)
            items = [("left", lift * 0.5), ("right", lift * 0.5)] + ([("both", -lift)] if fix else [])
            for index, (attribute, weight) in enumerate(items, start=1):
                _connect(owner + "." + attribute, "{}.input[{}]".format(height, index))
                height.getPlug("weight")[index].set(weight)
            if fix:
                node = _joint(name + "_centerOut", root, translate=(0, 6.0, 0))
                _set(node, "radius", 0.6)
                _color(node)
            else:
                node = _locator(name + "_plainCenter", root, translate=(0, 6.0, -0.5))
                _set(node, "overrideEnabled", True)
                _set(node, "overrideColor", 13)
            _connect("{}.output".format(height), node + ".translateY")
            centers[role] = node
        _set(controls["right"], "translateY", 1.0)
        for attribute, x in (("both", -1.0), ("leftHalf", 1.0)):
            marker = _locator("{}_{}".format(name, attribute), root, translate=(x, 9.0, 0))
            _color(marker)
            for axis in "XYZ":
                _connect(owner + "." + attribute, marker + ".scale" + axis)
        return setup, controls["left"]

    @classmethod
    def _virtualChain(cls, name, root):
        """同じ親(``_ctrls``)の下に兄弟として並べた尻尾の4つのコントロール(locator)。仮想のFK階層でつないで
        あるので、根元のコントロールを回すと先のコントロールがすべて付いてくる(アウトライナー上は平らなまま)。
        各コントロールの中の緑のjointは次のコントロールまでの骨を表す。containerの ``follow1`` 〜 ``follow3`` を
        0へ下げると、そのつなぎだけ前のコントロールを追わなくなる。"""
        from .setups import VirtualChain

        group = _transform(name + "_ctrls", root, translate=(0, 6, 0))
        length, bend = 2.5, 12.0
        controls, x, y, angle = [], 0.0, 0.0, 0.0
        for index in range(4):
            control = _locator("{}_ctrl{}".format(name, index), group, translate=(x, y, 0))
            _set(control, "rotate", (0, 0, angle))
            if index < 3:
                bone = _joint("{}_bone{}".format(name, index), control)
                for joint in (bone, _tip(bone, "{}_bone{}Tip".format(name, index), (length, 0, 0))):
                    _color(joint)
            controls.append(control)
            x += length * math.cos(math.radians(angle))
            y += length * math.sin(math.radians(angle))
            angle -= bend
        setup = VirtualChain.create(controls, name=name)
        return setup, controls[0]

    @classmethod
    def _stickyControl(cls, name, root):
        """2本のjointでスキンした平面(顔の皮膚の代わり)と、その表面に貼り付いた緑のコントロール。
        下のjointを回すと表面が曲がり、コントロールは表面の同じ場所に付いていく(コントロール自体も表面の上で動かせる)。"""
        from .setups import ControlShape, StickyControl

        surface = _transform(name + "_skin", root)
        plane = mlib.createNode("polyPlane", name=name + "_plane", skipSelect=True)
        for attribute, value in (("width", 6.0), ("height", 8.0), ("subdivisionsWidth", 6),
                                 ("subdivisionsHeight", 8)):
            plane.getPlug(attribute).set(value)
        plane.getPlug("axis").set((0.0, 0.0, 1.0))
        shape = mlib.createNode("mesh", name=name + "_skinShape", parent=surface, skipSelect=True)
        plane.getPlug("output").connectTo(shape.getPlug("inMesh"))
        # 材質の無いメッシュは画面で緑一色になるため、既定の材質(initialShadingGroup)へ入れる。
        mlib.nodes.Node("initialShadingGroup").addMembers(shape)
        top = _joint(name + "_top", root, translate=(0, 4, 0))
        bottom = _joint(name + "_bottom", top, translate=(0, -4, 0))
        _tip(bottom, name + "_bottomTip", (0, -4, 0))
        mlib.bindSkin([top, bottom], surface)
        control = _transform(name + "_ctrl", root, translate=(1.0, -2.0, 0.3))
        circle = [(0.5 * x, 0.5 * y, 0) for x, y in ((0, 1), (1, 0), (0, -1), (-1, 0), (0, 1))]
        ControlShape.replaceCurves(control, circle, [0, 1, 2, 3, 4], degree=1, name=name + "_ctrl")
        _color(control)
        setup = StickyControl.create(surface, control, name=name)
        return setup, bottom

    @classmethod
    def _fkIkChain(cls, name, root):
        """尻尾の6関節のFK(joint)とIK(Spline IKのjoint)。IKの先端のlocatorを動かすと、blend=0.5の出力(緑)が
        FKとIKの中間の弧を描く。containerのblendで切り替え、FK・IKの表示は fkVisibility・ikVisibility に従う。"""
        from .setups import FkIkChain, SplineIK

        hip = _transform(name + "_hip", root, translate=(0, 5, 0))
        chains = {}
        for role in ("fk", "ik"):
            joints, parent = [], hip
            for index in range(6):
                joint = _joint("{}_{}{}".format(name, role, index), parent, translate=(1.5 if index else 0, 0, 0))
                joints.append(joint)
                parent = joint
            chains[role] = [_longName(joint) for joint in joints]
        controls = [_locator("{}_ikCtrl{}".format(name, index), root, translate=(index * 2.5, 5, 0))
                    for index in range(4)]
        SplineIK.create(chains["ik"], controls, hip, name=name + "_spline")
        setup = FkIkChain.create(chains["fk"], chains["ik"], name=name, blend=0.5)
        _connect(str(setup.container) + ".fkVisibility", chains["fk"][0] + ".visibility")
        for control in controls:
            _connect(str(setup.container) + ".ikVisibility", control + ".visibility")
        for index in range(6):
            tips = ((1.5, 0, 0),) if index == 5 else ()
            _output("{}_tail{}Out".format(name, index), root, "{}.matrix{}".format(setup.container, index), tips)
        return setup, controls[-1]

    @classmethod
    def _slidingFk(cls, name, root):
        """尻尾の6関節と、その上に浮かせた2つのコントロール(locator)。コントロールを回すと、containerの
        position0・position1(チェーン上の位置)の近くの節へ回転が分かれ、出力(緑)が曲がる。"""
        from .setups import SlidingFk

        hip = _transform(name + "_hip", root, translate=(0, 5, 0))
        joints, parent = [], hip
        for index in range(6):
            joint = _joint("{}_tail{}".format(name, index), parent, translate=(1.5 if index else 0, 0, 0))
            joints.append(joint)
            parent = joint
        controls = [_locator("{}_ctrl{}".format(name, index), root, translate=(7.5 * position, 8, 0))
                    for index, position in enumerate((0.25, 0.75))]
        setup = SlidingFk.create(joints, controls, name=name, positions=(0.25, 0.75))
        for index in range(6):
            tips = ((1.5, 0, 0),) if index == 5 else ()
            _output("{}_tail{}Out".format(name, index), root, "{}.matrix{}".format(setup.container, index), tips)
        return setup, controls[0]

    @classmethod
    def _swingLimit(cls, name, root):
        """肩のjoint。入力を回すと、楕円の範囲で柔らかく止まった向き(緑)になる。"""
        from .setups import SwingLimit

        shoulder, source = cls._limitInput(name, root)
        setup = SwingLimit.create(source, name=name, axis="x", limit1=60.0, limit2=30.0, softness=0.2)
        cls._limitOutput(name, shoulder, setup)
        return setup, source

    @classmethod
    def _asymmetricSwingLimit(cls, name, root):
        """肩のjoint。入力を回すと、向きごとに上限の違う範囲で止まった向き(緑)になる。"""
        from .setups import AsymmetricSwingLimit

        shoulder, source = cls._limitInput(name, root)
        setup = AsymmetricSwingLimit.create(source, name=name, axis="x")
        cls._limitOutput(name, shoulder, setup)
        return setup, source

    @classmethod
    def _twistLimit(cls, name, root):
        """前腕のjoint。入力をrotateXでねじると、-45〜45度で柔らかく止まったねじれ(緑)になる。"""
        from .setups import TwistLimit

        shoulder, source = cls._limitInput(name, root)
        setup = TwistLimit.create(source, name=name, axis="x", minimum=-45.0, maximum=45.0, softness=0.2)
        cls._limitOutput(name, shoulder, setup)
        return setup, source

    @classmethod
    def _swingTwist(cls, name, root):
        """joint。入力を回すと、ねじれを除いたSwingだけの向き(緑)になる。"""
        from .setups import SwingTwist

        shoulder, source = cls._limitInput(name, root)
        setup = SwingTwist.create(source, name=name, axis="x")
        cls._limitOutput(name, shoulder, setup, "swingMatrix")
        return setup, source

    @classmethod
    def _rotationFollow(cls, name, root):
        """joint。入力を回すと、回転の半分だけ追従した向き(緑)になる。"""
        from .setups import RotationFollow

        shoulder, source = cls._limitInput(name, root)
        setup = RotationFollow.create(source, name=name, mode="full", axis="x", ratio=0.5)
        cls._limitOutput(name, shoulder, setup)
        return setup, source

    @classmethod
    def _coneReader(cls, name, root):
        """肩と上腕。上腕を回すと、コーンとの一致度(containerのweight)が1から0へ変わる。"""
        from .setups import ConeReader

        shoulder = _joint(name + "_shoulder", root, translate=(0, 10, 0))
        arm = _joint(name + "_upperArm", shoulder, translate=(2, 0, 0))
        _tip(arm, name + "_upperArmTip", (3, 0, 0))
        setup = ConeReader.create(arm, shoulder, name=name, coneAngle=45.0, size=2.0)
        return setup, arm

    @staticmethod
    def _limitInput(name, root):
        """制限・分解のサンプルに共通の、親transformと入力jointを作る。"""
        shoulder = _transform(name + "_shoulder", root, translate=(0, 10, 0))
        source = _joint(name + "_input", shoulder)
        return shoulder, source

    @staticmethod
    def _limitOutput(name, shoulder, setup, attribute="matrix"):
        """制限のサンプルに共通の、行列の出力を受ける緑のjointと入力の骨の先を作る。

        Args:
            name (str): 名前の接頭辞。
            shoulder (str): 入力と出力の親。
            setup (object): セットアップの生成結果。
            attribute (str): 出力の行列のアトリビュート名。
        """
        source = shoulder + "|" + name + "_input"
        _tip(source, name + "_inputTip", (3, 0, 0))
        _tip(source, name + "_inputFin", (0, 0.8, 0))
        _output(name + "_out", shoulder, str(setup.container) + "." + attribute, ((3, 0, 0), (0, 0.8, 0)))


def _longName(node):
    """ノードのフルパス。"""
    return mlib.nodes.Node(str(node)).getFullName()


def _set(node, attribute, value):
    """アトリビュートへUI単位(cm・度)の値を書き込む。"""
    mlib.nodes.Node(node).getPlug(attribute).set(value, uiUnits=True)


def _connect(source, destination):
    """2つのplugを接続する。"""
    mlib.getPlug(source).connectTo(destination)


def _create(kind, name, parent, translate=(0, 0, 0), rotate=(0, 0, 0)):
    """parentの下(Noneならワールド)にtransform系のノードを作り、フルパスを返す。"""
    flags = {} if parent is None else {"parent": parent}
    node = mlib.createNode(kind, name=name, skipSelect=True, **flags).getFullName()
    _set(node, "translate", tuple(translate))
    _set(node, "rotate", tuple(rotate))
    return node


def _transform(name, parent, translate=(0, 0, 0), rotate=(0, 0, 0)):
    """parentの下にtransformを作り、フルパスを返す。"""
    return _create("transform", name, parent, translate, rotate)


def _joint(name, parent, translate=(0, 0, 0), rotate=(0, 0, 0)):
    """parentの下にjointを作り、フルパスを返す。表示の半径は骨の長さ(数cm)に合わせて小さくする。"""
    node = _create("joint", name, parent, translate, rotate)
    _set(node, "radius", 0.4)
    return node


def _locator(name, parent, translate=(0, 0, 0)):
    """parentの下にlocatorのシェイプを持つtransformを作り、フルパスを返す。"""
    node = _transform(name, parent, translate)
    mlib.createNode("locator", name=name + "Shape", parent=node, skipSelect=True)
    return node


def _chain(name, parent, items):
    """ワールド位置を指定したjointの親子の列を作る。jointの向き(jointOrient)は0のまま。

    Args:
        name (str): 名前の接頭辞。
        parent (str): 先頭のjointの親。
        items (Sequence[tuple[str, tuple[float, float, float]]]): (役割名, ワールド位置)の列。

    Returns:
        list[str]: jointのフルパス。
    """
    joints, current = [], parent
    for role, position in items:
        joint = _joint(name + "_" + role, current)
        mlib.nodes.Node(joint).setTranslation(position, worldSpace=True)
        joints.append(joint)
        current = joint
    return [_longName(joint) for joint in joints]


def _tip(parent, name, translate):
    """表示用に、parentの下へ骨の先を示すjointを作る。"""
    return _joint(name, parent, translate=translate)


def _color(node):
    """ノードを出力の色(緑)で表示する。"""
    _set(node, "overrideEnabled", True)
    _set(node, "overrideColor", _OUTPUT_COLOR)


def _output(name, parent, plug, tips=()):
    """出力の行列を ``offsetParentMatrix`` で受ける緑のjointを作る。

    Args:
        name (str): jointの名前。
        parent (str): 入力と同じ親。
        plug (str): 接続する行列のplug。
        tips (Sequence[tuple[float, float, float]]): 向きを示す子jointの位置。

    Returns:
        str: 出力jointのフルパス。
    """
    node = _joint(name, parent)
    _set(node, "radius", 0.6)
    _color(node)
    _connect(plug, node + ".offsetParentMatrix")
    for index, translate in enumerate(tips):
        _tip(node, "{}Tip{}".format(name, index), translate)
    return node
