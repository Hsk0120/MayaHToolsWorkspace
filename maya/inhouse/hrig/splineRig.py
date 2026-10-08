"""背骨・尻尾のFK骨列へ、標準Spline IKを重ねるモジュール。"""
from hlib.maths import MSpace

from maya import cmds

from functools import partial
import math
import re

import hlib
from hlib.maths import Matrix, EulerRotation

from hrig.setups import SplineIK
from hlib.decorator import undoTransaction


class SplineRig:
    """FK・Spline IK・変形骨を別階層で保持する。"""

    _jobs = {}
    _busy = False

    def __init__(self, root):
        """保存済みモジュールを参照する。

        Args:
            root (str | Node): モジュールルート。
        """
        self.root = hlib.getNode(root)
        if not self.root.hasAttr("hrigSplineDefinition"):
            raise ValueError("Not an hrig spline module")

    @classmethod
    @undoTransaction("hrig.SplineRig.create")
    def create(cls, name="spine01", joint_count=7, control_count=4, length=10.0, axis="y"):
        """正軸上の骨列と独立したカーブコントロールを作成する。

        Args:
            name (str): 一意なモジュール名。
            joint_count (int): 末端を含む3〜64本。
            control_count (int): 3次カーブのCV数。4〜32個。
            length (float): 現在のシーン単位での骨列長。
            axis (str): 初期配置方向x/y/z。骨の長手軸はローカルX。

        Returns:
            SplineRig: 作成したモジュール。
        """
        if (
            not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name)
            or cmds.objExists(name)
            or [item.getName() for item in hlib.ls(name + "_*")]
        ):
            raise ValueError("Use a unique unnamespaced module name")
        if type(joint_count) is not int or not 3 <= joint_count <= 64:
            raise ValueError("joint_count must be 3..64")
        if type(control_count) is not int or not 4 <= control_count <= 32:
            raise ValueError("control_count must be 4..32")
        if axis not in ("x", "y", "z") or not math.isfinite(length) or length <= 0:
            raise ValueError("Use axis x/y/z and a positive finite length")
        root = hlib.createNode("transform", name=name, skipSelect=True)
        root.addAttr(longName="hrigSplineDefinition", dataType="string").set(
            hlib.json.JsonText.dumps(
                dict(
                    version=1,
                    joint_count=joint_count,
                    control_count=control_count,
                    length=length,
                    axis=axis,
                )
            )
        )
        root.setAttrFlags(["hrigSplineDefinition"], locked=True)
        for attr in ("fk", "ik", "deform", "controls"):
            root.addAttr(longName=attr, attributeType="message", multi=True)
        for attr in ("graph", "fkGroup", "ikGroup", "deformGroup", "controlGroup", "setupGroup"):
            root.addAttr(longName=attr, attributeType="message")
        for attr, labels, value in (("mode", "FK:SplineIK", 1), ("lod", "Low:Full", 1)):
            root.addAttr(
                longName=attr, attributeType="enum", enumName=labels, defaultValue=value
            )
        root.addAttr(longName="enabled", attributeType="bool", defaultValue=True)
        root.setAttrFlags(["mode", "lod", "enabled"], channelBox=True)
        groups = {}
        for role in ("fk", "ik", "deform", "control", "setup"):
            group = hlib.createNode(
                "transform", name=name + "_" + role + "_grp", parent=root, skipSelect=True
            )
            group.getPlug("message").connectTo(root.getPlug(role + "Group"))
            group.setAttrFlags(["translate", "rotate", "scale"], locked=True, keyable=False)
            groups[role] = group
        groups["ik"].getPlug("visibility").set(False)
        groups["setup"].getPlug("visibility").set(False)
        rig = cls(root)
        angle = math.pi / 2
        orient = {"x": (0, 0, 0), "y": (0, 0, angle), "z": (0, -angle, 0)}[axis]
        for role in ("fk", "ik", "deform"):
            parent = groups[role]
            for i in range(joint_count):
                joint = hlib.createNode(
                    "joint",
                    name="{}_{}{:02d}_jnt".format(name, role, i + 1),
                    parent=parent,
                    skipSelect=True,
                )
                joint.getPlug("translateX").set(hlib.common.units.distanceFromUi(length / (joint_count - 1)) if i else 0)
                joint.getPlug("jointOrient").set(orient if i == 0 else (0, 0, 0))
                joint.getPlug("segmentScaleCompensate").set(False)
                joint.getPlug("radius").set(0.2)
                joint.getPlug("message").connectTo(root.getPlug(role)[i])
                if role == "fk":
                    cls._shape(joint, length * 0.035, (1, 0, 0), 17)
                    joint.setAttrFlags(["scale", "visibility"], locked=True, keyable=False)
                    if i:
                        joint.setAttrFlags(["translate"], locked=True, keyable=False)
                parent = joint
        normal = tuple(1 if a == axis else 0 for a in "xyz")
        for i in range(control_count):
            offset = hlib.createNode(
                "transform",
                name="{}_spline{:02d}_grp".format(name, i + 1),
                parent=groups["control"],
                skipSelect=True,
            )
            offset.getPlug("translate").set(
                tuple(hlib.common.units.distanceFromUi(v * length * i / (control_count - 1)) for v in normal)
            )
            control = hlib.createNode(
                "transform",
                name="{}_spline{:02d}_ctrl".format(name, i + 1),
                parent=offset,
                skipSelect=True,
            )
            cls._shape(control, length * 0.06, normal, 18)
            control.setAttrFlags(["scale", "visibility"], locked=True, keyable=False)
            if i not in (0, control_count - 1):
                control.setAttrFlags(["rotate"], locked=True, keyable=False)
            offset.setAttrFlags(["translate", "rotate", "scale"], locked=True, keyable=False)
            control.getPlug("message").connectTo(root.getPlug("controls")[i])
        graph = SplineIK.create(
            rig.getMembers("ik"),
            rig.controls(),
            groups["setup"],
            name + "_splineGraph",
            "y" if axis == "z" else "z",
        )
        graph.container.getPlug("message").connectTo(root.getPlug("graph"))
        rig.update()
        from .channel_controls import install

        install()
        return rig

    @staticmethod
    def _shape(node, radius, normal, color):
        """コントロールへ円形シェイプを追加する。

        Args:
            node (Node): 操作ノード。
            radius (float): 表示半径。
            normal (tuple): 円の法線。
            color (int): Mayaカラー番号。
        """
        from hrig.setups import ControlShape

        ControlShape.circle(node, radius=radius, normal=normal, color=color)

    def getMembers(self, attr):
        """message配列を順に解決する。

        Args:
            attr (str): fk/ik/deform/controls。

        Returns:
            list[Node]: 登録ノード。
        """
        return list(self.root.getPlug(attr).getSourceNodes().values())

    def controls(self):
        """カーブ用コントロールを根元から取得する。

        Returns:
            list[Node]: 操作ノード。
        """
        return self.getMembers("controls")

    def getJoints(self):
        """スキン対象の変形骨だけを取得する。

        Returns:
            tuple[str]: 完全名。
        """
        from .tweakLayer import TweakLayer

        return tuple(n.getFullName() for n in self.getMembers("deform")) + TweakLayer(self).getJoints()

    def graph(self):
        """Spline IK計算グラフを取得する。

        Returns:
            SplineIK: 保存済みグラフ。
        """
        return SplineIK(self.root.getPlug("graph").getSourceWithConversion().getNode())

    def mode(self):
        """選択モードを取得する。

        Returns:
            str: fkまたはik。
        """
        return "ik" if self.root.getPlug("mode").get() else "fk"

    def lod(self):
        """構成LODを取得する。

        Returns:
            int: 0=Low、1=Full。
        """
        return self.root.getPlug("lod").get()

    def layer_enabled(self, layer="spline"):
        """Splineレイヤーの使用設定を取得する。

        Args:
            layer (str): splineまたはstretch。

        Returns:
            bool: 使用設定。
        """
        if layer == "stretch":
            return self.root.hasAttr("hrigEnabled_stretch") and bool(
                self.root.getPlug("hrigEnabled_stretch").get()
            )
        if layer != "spline":
            raise ValueError("Unknown layer: " + layer)
        return bool(self.root.getPlug("enabled").get())

    def add_stretch(self):
        """伸縮・体積補正レイヤーを追加する。

        Returns:
            Node: 設定グループ。
        """
        from .splineStretchLayer import SplineStretchLayer

        return SplineStretchLayer(self).add()

    def active(self):
        """実際にSpline IKを使用するか取得する。

        Returns:
            bool: IKモード・Full LOD・使用設定がすべて有効か。
        """
        return self.mode() == "ik" and self.lod() == 1 and self.layer_enabled()

    @undoTransaction("hrig.SplineRig.set_mode")
    def set_mode(self, mode):
        """構成モードを切り替える。姿勢合わせは行わない。

        Args:
            mode (str): fk/ik。
        """
        if mode not in ("fk", "ik"):
            raise ValueError("Use fk or ik")
        self.root.getPlug("mode").set(int(mode == "ik"))
        self.update()

    @undoTransaction("hrig.SplineRig.match_fk")
    def match_fk(self):
        """現在の変形骨の姿勢をFKへコピーする。キーの自動作成はしない。"""
        values = [
            {attr: n.getPlug(attr).get() for attr in ("translate", "rotate", "scale")}
            for n in self.getMembers("deform")
        ]
        for joint, data in zip(self.getMembers("fk"), values):
            for attr, row in data.items():
                parent_locked = joint.getPlug(attr).isLocked()
                if parent_locked:
                    joint.setAttrFlags([attr], locked=False)
                try:
                    for axis, value in zip("XYZ", row):
                        plug = joint.getPlug(attr + axis)
                        locked = plug.isLocked()
                        if locked:
                            joint.setAttrFlags([attr + axis], locked=False)
                        try:
                            plug.set(value)
                        finally:
                            if locked:
                                joint.setAttrFlags([attr + axis], locked=True)
                finally:
                    if parent_locked:
                        joint.setAttrFlags([attr], locked=True)

    @undoTransaction("hrig.SplineRig.match_ik")
    def match_ik(self, tolerance=None):
        """現在の変形骨へSplineコントロールを近似配置する。

        Args:
            tolerance (float | None): 現在の距離単位での最大許容位置誤差。
                Noneなら近似結果を採用。超過時はUndoで元へ戻す。

        Returns:
            float: 実際のIK評価後の最大関節位置誤差。モードとLODは維持する。

        Note:
            FKの任意の折れ角・中間Twist・断面scaleは完全復元できない。
            キーは生成しない。両端のUp方向を合わせ、内部のひねりは補間する。
        """
        from hlib.common.curveFit import CurveFit

        if tolerance is not None and (not math.isfinite(tolerance) or tolerance < 0):
            raise ValueError("Tolerance must be non-negative finite")
        if self.lod() != 1 or not self.layer_enabled():
            raise ValueError("Enable Spline and Full LOD before matching")
        joints = self.getMembers("deform")
        matrices = [Matrix(n.getMatrix(ws=True)) for n in joints]
        points = [[m[12], m[13], m[14]] for m in matrices]
        controls = self.controls()
        cvs = CurveFit.fit(points, len(controls))
        axis = hlib.json.JsonText.loads(self.root.getPlug("hrigSplineDefinition").get())["axis"]
        rest = EulerRotation(
            0, -math.pi / 2 if axis == "z" else 0, math.pi / 2 if axis == "y" else 0
        ).asMatrix()
        for i, (control, point) in enumerate(zip(controls, cvs)):
            parent = hlib.getNode(
                [
                    item.getFullName()
                    for item in [
                        hlib.getNode(value)
                        for value in (
                            cmds.listRelatives(control.getFullName(), parent=True, fullPath=True)
                            or []
                        )
                    ]
                ][0]
            )
            parent_inverse = Matrix(parent.getMatrix(ws=True)).inverse()
            local = parent_inverse.transformPoint(point)
            for a, value in zip("XYZ", (local.x, local.y, local.z)):
                control.getPlug("translate" + a).set(value)
            if i in (0, len(controls) - 1):
                source = matrices[0 if i == 0 else -1]
                rotation = source.quaternion.asUnitMatrix()
                local_rotation = Matrix(rest.inverse() * rotation * parent_inverse).euler
                local_rotation.reorderIt(control.getPlug("rotateOrder").get())
                for a, value in zip("XYZ", local_rotation):
                    control.getPlug("rotate" + a).set(value)
        mode = self.mode()
        try:
            self.set_mode("ik")
            errors = []
            for target, joint in zip(points, joints):
                matrix = joint.getMatrix(ws=True)
                errors.append(math.sqrt(sum((target[i] - matrix[12 + i]) ** 2 for i in range(3))))
            error = hlib.common.units.distanceToUi(max(errors))
        finally:
            self.set_mode(mode)
        if tolerance is not None and error > tolerance:
            raise ValueError(
                "Spline fit error {:.6g} exceeds tolerance {:.6g}".format(error, tolerance)
            )
        return error

    @undoTransaction("hrig.SplineRig.set_lod")
    def set_lod(self, value):
        """LowではFKへ戻す。

        Args:
            value (int): 0/1。
        """
        if value not in (0, 1):
            raise ValueError("Use lod 0 or 1")
        self.root.getPlug("lod").set(value)
        self.update()

    @undoTransaction("hrig.SplineRig.set_layer_enabled")
    def set_layer_enabled(self, layer, enabled):
        """Splineレイヤーを切り替える。

        Args:
            layer (str): splineまたはstretch。
            enabled (bool): 使用設定。
        """
        self.layer_enabled(layer)
        if layer == "stretch" and not self.root.hasAttr("hrigEnabled_stretch"):
            raise ValueError("Add the stretch layer first")
        self.root.getPlug("hrigEnabled_stretch" if layer == "stretch" else "enabled").set(
            bool(enabled)
        )
        self.update()

    @undoTransaction("hrig.SplineRig.update")
    def update(self):
        """使用する骨列だけを変形骨へ接続し、不要なIKを停止する。"""
        active = self.active()
        self.graph().set_enabled(active)
        sources = self.getMembers("ik" if active else "fk")
        for source, joint in zip(sources, self.getMembers("deform")):
            for attr in ("translate", "rotate"):
                target = joint.getPlug(attr)
                if target.getSourceWithConversion() is not None:
                    target.disconnect(target.getSourceWithConversion())
                source.getPlug(attr).connectTo(target)
        self.root.getPlug("fkGroup").getSourceWithConversion().getNode().getPlug("visibility").set(not active)
        self.root.getPlug("controlGroup").getSourceWithConversion().getNode().getPlug("visibility").set(active)
        from .splineStretchLayer import SplineStretchLayer

        SplineStretchLayer(self).update()
        from .tweakLayer import TweakLayer

        TweakLayer(self).update()

    @classmethod
    def refresh_jobs(cls):
        """GUIの属性監視を復元する。バッチでは明示APIを使う。"""
        if cmds.about(batch=True):
            return
        for key, jobs in list(cls._jobs.items()):
            if not [item.getName() for item in hlib.ls(key)] or not jobs.exists():
                jobs.stop()
                del cls._jobs[key]
        for attr in [
            item.getFullName() for item in hlib.ls("*.hrigSplineDefinition", recursive=True)
        ] or []:
            rig = cls(attr.rsplit(".", 1)[0])
            key = rig.root.getUuid()
            if key in cls._jobs:
                continue
            jobs = hlib.common.ScriptJobs()
            attrs = ["mode", "lod", "enabled"]
            if rig.root.hasAttr("hrigEnabled_stretch"):
                attrs.append("hrigEnabled_stretch")
            for name in attrs:
                jobs.add(
                    name,
                    attribute=rig.root.getPlug(name),
                    callback=partial(cls._changed, key),
                    kill_with_scene=True,
                    compress_undo=True,
                )
            cls._jobs[key] = jobs

    @classmethod
    def _changed(cls, key):
        """接続の差があるときだけ反映し、Undo/Redoの履歴を維持する。

        Args:
            key (str): ルートUUID。
        """
        roots = [item.getFullName() for item in hlib.ls(key, long=True)] or []
        if cls._busy or not roots:
            return
        cls._busy = True
        try:
            rig = cls(roots[0])
            expected = rig.getMembers("ik" if rig.active() else "fk")[0].getPlug("rotate")
            actual = rig.getMembers("deform")[0].getPlug("rotate").getSourceWithConversion()
            from .splineStretchLayer import SplineStretchLayer

            if (
                actual is None
                or actual.mplug() != expected.mplug()
                or SplineStretchLayer(rig).needs_update()
            ):
                rig.update()
        finally:
            cls._busy = False

    @undoTransaction("hrig.SplineRig.delete")
    def delete(self):
        """スキン未使用なら所有グラフと階層を削除する。"""
        if any(hlib.getNode(joint).getConnections(type="skinCluster") for joint in self.getJoints()):
            raise ValueError("Unbind the spline before deleting its module")
        from .splineStretchLayer import SplineStretchLayer

        settings = SplineStretchLayer(self).settings()
        if settings is not None:
            hlib.delete(settings.getPlug("graph").getSourceWithConversion().getNode())
        hlib.delete(self.graph().container)
        hlib.delete(self.root)
