"""Spline IKへ曲線長による伸縮と断面の体積補正を追加する。"""

from maya import cmds

import hlib

from hrig.setups import LengthCompensation
from hlib.decorators.undo import undo_transaction


class SplineStretchLayer:
    """計測・計算・出力接続を一つの任意レイヤーとして管理する。"""

    def __init__(self, rig):
        """対象モジュールを保持する。

        Args:
            rig (SplineRig): 対象。
        """
        self.rig = rig

    def settings(self):
        """設定グループを取得する。

        Returns:
            Node | None: 未追加ならNone。
        """
        root = self.rig.root
        source = root.plug("stretchGroup").source() if root.has_attribute("stretchGroup") else None
        return source.node if source is not None else None

    @staticmethod
    def _node(owner, kind, role):
        """レイヤー固有の計測ノードを所有containerへ追加する。

        Args:
            owner (Node): 所有container。
            kind (str): 型。
            role (str): 用途。

        Returns:
            Node: 生成ノード。
        """
        return hlib.nodes.Container(owner).create_node(kind, name=owner.name() + "_" + role)

    @undo_transaction("hrig.SplineStretchLayer.add")
    def add(self):
        """現在の骨長を基準に伸縮レイヤーを追加する。

        Returns:
            Node: Channel Boxで編集する設定グループ。

        Note:
            スキン済み骨には構造変更を行わず、追加を拒否する。
        """
        if self.settings() is not None:
            return self.settings()
        rig, root = self.rig, self.rig.root
        if any(hlib.getNode(j).connections(type="skinCluster") for j in rig.joints()):
            raise ValueError("Add stretch before binding the spline")
        lengths = [
            hlib.general.Units.distance_from_ui(hlib.getAttr(j.full_name() + ".translateX"))
            for j in rig.members("ik")[1:]
        ]
        graph = LengthCompensation.create(sum(lengths), root.name() + "_stretchGraph")
        owner = graph.container
        group = hlib.createNode(
            "transform", name=root.name() + "_stretch_grp", parent=root, skipSelect=True
        )
        group.set_attribute_flags(
            ["translate", "rotate", "scale", "visibility"], locked=True, keyable=False
        )
        group.add_attribute(long_name="graph", attribute_type="message")
        owner.plug("message").connect(group.plug("graph"))
        group.add_attribute(long_name="restLengths", data_type="string").set(
            hlib.json.JsonText.dumps(lengths)
        )
        group.add_attribute(long_name="outputs", attribute_type="message", multi=True)
        group.add_attribute(long_name="measurement", attribute_type="message")
        root.add_attribute(long_name="stretchGroup", attribute_type="message")
        group.plug("message").connect(root.plug("stretchGroup"))
        root.add_attribute(long_name="hrigEnabled_stretch", attribute_type="bool", default_value=True)
        root.set_attribute_flags(["hrigEnabled_stretch"], channel_box=True)
        for attr, value, low, high in (
            ("stretch", 1, 0, 1),
            ("squash", 1, 0, 1),
            ("volume", 1, 0, 1),
            ("minSquash", 0.1, 0.01, 1),
            ("maxStretch", 2, 1, 100),
        ):
            group.add_attribute(
                long_name=attr,
                attribute_type="double",
                default_value=value,
                minValue=low,
                maxValue=high,
                keyable=True,
            )
            group.plug(attr).connect(owner.plug(attr))
        curve = rig.graph().member("curve")
        shape = hlib.getNode(
            [
                item.full_name()
                for item in [
                    hlib.getNode(value)
                    for value in (
                        cmds.listRelatives(curve.full_name(), shapes=True, fullPath=True) or []
                    )
                ]
            ][0]
        )
        measure = self._node(owner, "curveInfo", "localLength")
        # localカーブならモジュールの正の均等scaleは長さ比へ混入しない。
        shape.plug("local").connect(measure.plug("inputCurve"))
        curve_units = self._node(owner, "unitConversion", "curveLengthCm")
        measure.plug("arcLength").connect(curve_units.plug("input"))
        curve_units.plug("conversionFactor").set(1)
        curve_units.plug("output").connect(owner.plug("inputLength"))
        measure.plug("message").connect(group.plug("measurement"))
        for i, length in enumerate(lengths):
            multiply = self._node(owner, "multiplyDivide", "boneLength" + str(i))
            multiply.plug("input1X").set(length)
            owner.plug("lengthScale").connect(multiply.plug("input2X"))
            units = self._node(owner, "unitConversion", "lengthUnits" + str(i))
            multiply.plug("outputX").connect(units.plug("input"))
            units.plug("conversionFactor").set(1)
            units.plug("message").connect(group.plug("outputs[{}]".format(i)))
        # 親の断面scaleを子が累積しないよう、Maya標準のSSCとinverseScaleを使う。
        for role in ("fk", "deform"):
            bones = rig.members(role)
            for i, bone in enumerate(bones):
                bone.plug("segmentScaleCompensate").set(True)
                if i:
                    bones[i - 1].plug("scale").connect(bone.plug("inverseScale"), force=True)
        rig.update()
        jobs = rig._jobs.pop(root.uuid(), None)
        if jobs is not None:
            jobs.stop()
        rig.refresh_jobs()
        return group

    def active(self):
        """伸縮が実際に有効か取得する。

        Returns:
            bool: IK・LOD・設定がすべて有効か。
        """
        return (
            self.settings() is not None and self.rig.active() and self.rig.layer_enabled("stretch")
        )

    def update(self):
        """無効な計測と長さ出力を切断し、元のIK骨長へ戻す。"""
        group = self.settings()
        if group is None:
            return
        active = self.active()
        owner = group.plug("graph").source().node
        measure = group.plug("measurement").source().node
        curve = self.rig.graph().member("curve")
        target = measure.plug("inputCurve")
        if active and target.source() is None:
            shape = hlib.getNode(
                [
                    item.full_name()
                    for item in [
                        hlib.getNode(value)
                        for value in (
                            cmds.listRelatives(curve.full_name(), shapes=True, fullPath=True) or []
                        )
                    ]
                ][0]
            )
            shape.plug("local").connect(target)
        elif not active and target.source() is not None:
            target.source().disconnect(target)
        measure.plug("nodeState").set(0 if active else 2)
        lengths = hlib.json.JsonText.loads(group.plug("restLengths").get())
        for i, (joint, length) in enumerate(zip(self.rig.members("ik")[1:], lengths)):
            target = joint.plug("translateX")
            if target.source() is not None:
                target.source().disconnect(target)
            if active:
                group.plug("outputs[{}]".format(i)).source().node.plug("output").connect(target)
            else:
                target.set(hlib.general.Units.distance_to_ui(length))
        for source, joint in zip(
            self.rig.members("ik" if self.rig.active() else "fk"), self.rig.members("deform")
        ):
            for axis in "XYZ":
                target = joint.plug("scale" + axis)
                if target.source() is not None:
                    target.source().disconnect(target)
                output = (
                    owner.plug("volumeScale")
                    if active and axis != "X"
                    else source.plug("scale" + axis)
                )
                output.connect(target)

    def needs_update(self):
        """監視で空のUndo編集を発生させないよう接続差を調べる。

        Returns:
            bool: 設定と実接続が異なるか。
        """
        group = self.settings()
        return (
            group is not None
            and (self.rig.members("ik")[1].plug("translateX").source() is not None) != self.active()
        )
