"""Spline IKへ曲線長による伸縮と断面の体積補正を追加する。"""

from maya import cmds

import hlib

from hrig.setups import LengthCompensation
from hlib.decorators.undo import undoTransaction


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
        source = root.plug("stretchGroup").sourceWithConversion() if root.hasAttr("stretchGroup") else None
        return source.node() if source is not None else None

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
        return hlib.nodes.Container(owner).createNode(kind, name=owner.name() + "_" + role)

    @undoTransaction("hrig.SplineStretchLayer.add")
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
            j.plug("translateX").get()
            for j in rig.members("ik")[1:]
        ]
        graph = LengthCompensation.create(sum(lengths), root.name() + "_stretchGraph")
        owner = graph.container
        group = hlib.createNode(
            "transform", name=root.name() + "_stretch_grp", parent=root, skipSelect=True
        )
        group.setAttributeFlags(
            ["translate", "rotate", "scale", "visibility"], locked=True, keyable=False
        )
        group.addAttr(longName="graph", attributeType="message")
        owner.plug("message").connectTo(group.plug("graph"))
        group.addAttr(longName="restLengths", dataType="string").set(
            hlib.json.JsonText.dumps(lengths)
        )
        group.addAttr(longName="outputs", attributeType="message", multi=True)
        group.addAttr(longName="measurement", attributeType="message")
        root.addAttr(longName="stretchGroup", attributeType="message")
        group.plug("message").connectTo(root.plug("stretchGroup"))
        root.addAttr(longName="hrigEnabled_stretch", attributeType="bool", defaultValue=True)
        root.setAttributeFlags(["hrigEnabled_stretch"], channelBox=True)
        for attr, value, low, high in (
            ("stretch", 1, 0, 1),
            ("squash", 1, 0, 1),
            ("volume", 1, 0, 1),
            ("minSquash", 0.1, 0.01, 1),
            ("maxStretch", 2, 1, 100),
        ):
            group.addAttr(
                longName=attr,
                attributeType="double",
                defaultValue=value,
                minValue=low,
                maxValue=high,
                keyable=True,
            )
            group.plug(attr).connectTo(owner.plug(attr))
        curve = rig.graph().member("curve")
        shape = hlib.getNode(
            [
                item.fullName()
                for item in [
                    hlib.getNode(value)
                    for value in (
                        cmds.listRelatives(curve.fullName(), shapes=True, fullPath=True) or []
                    )
                ]
            ][0]
        )
        measure = self._node(owner, "curveInfo", "localLength")
        # localカーブならモジュールの正の均等scaleは長さ比へ混入しない。
        shape.plug("local").connectTo(measure.plug("inputCurve"))
        curve_units = self._node(owner, "unitConversion", "curveLengthCm")
        measure.plug("arcLength").connectTo(curve_units.plug("input"))
        curve_units.plug("conversionFactor").set(1)
        curve_units.plug("output").connectTo(owner.plug("inputLength"))
        measure.plug("message").connectTo(group.plug("measurement"))
        for i, length in enumerate(lengths):
            multiply = self._node(owner, "multiplyDivide", "boneLength" + str(i))
            multiply.plug("input1X").set(length)
            owner.plug("lengthScale").connectTo(multiply.plug("input2X"))
            units = self._node(owner, "unitConversion", "lengthUnits" + str(i))
            multiply.plug("outputX").connectTo(units.plug("input"))
            units.plug("conversionFactor").set(1)
            units.plug("message").connectTo(group.plug("outputs")[i])
        # 親の断面scaleを子が累積しないよう、Maya標準のSSCとinverseScaleを使う。
        for role in ("fk", "deform"):
            bones = rig.members(role)
            for i, bone in enumerate(bones):
                bone.plug("segmentScaleCompensate").set(True)
                if i:
                    bones[i - 1].plug("scale").connectTo(bone.plug("inverseScale"), force=True)
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
        owner = group.plug("graph").sourceWithConversion().node()
        measure = group.plug("measurement").sourceWithConversion().node()
        curve = self.rig.graph().member("curve")
        target = measure.plug("inputCurve")
        if active and target.sourceWithConversion() is None:
            shape = hlib.getNode(
                [
                    item.fullName()
                    for item in [
                        hlib.getNode(value)
                        for value in (
                            cmds.listRelatives(curve.fullName(), shapes=True, fullPath=True) or []
                        )
                    ]
                ][0]
            )
            shape.plug("local").connectTo(target)
        elif not active and target.sourceWithConversion() is not None:
            target.disconnect(target.sourceWithConversion())
        measure.plug("nodeState").set(0 if active else 2)
        lengths = hlib.json.JsonText.loads(group.plug("restLengths").get())
        for i, (joint, length) in enumerate(zip(self.rig.members("ik")[1:], lengths)):
            target = joint.plug("translateX")
            if target.sourceWithConversion() is not None:
                target.disconnect(target.sourceWithConversion())
            if active:
                group.plug("outputs")[i].sourceWithConversion().node().plug("output").connectTo(target)
            else:
                target.set(length)
        for source, joint in zip(
            self.rig.members("ik" if self.rig.active() else "fk"), self.rig.members("deform")
        ):
            for axis in "XYZ":
                target = joint.plug("scale" + axis)
                if target.sourceWithConversion() is not None:
                    target.disconnect(target.sourceWithConversion())
                output = (
                    owner.plug("volumeScale")
                    if active and axis != "X"
                    else source.plug("scale" + axis)
                )
                output.connectTo(target)

    def needs_update(self):
        """監視で空のUndo編集を発生させないよう接続差を調べる。

        Returns:
            bool: 設定と実接続が異なるか。
        """
        group = self.settings()
        return (
            group is not None
            and (self.rig.members("ik")[1].plug("translateX").sourceWithConversion() is not None) != self.active()
        )
