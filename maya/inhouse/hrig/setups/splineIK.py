"""標準Spline IKと、コントロールからカーブへの接続を生成する。"""
from hlib.maths import MSpace

from maya import cmds

import hlib

from hlib.decorators.undo import undo_transaction


class SplineIK:
    """既存の骨とコントロールを入力とする、標準ノードの計算グラフ。"""

    def __init__(self, container):
        """保存済みグラフを参照する。

        Args:
            container (str | Node): 所有container。
        """
        self.container = hlib.nodes.Container(container)

    def member(self, name):
        """messageから構成ノードを取得する。

        Args:
            name (str): handle、curve、effector。

        Returns:
            Node: 参照先。
        """
        return self.container.plug(name).source().node

    @classmethod
    @undo_transaction("hrig.SplineIK.create")
    def create(cls, joints, controls, parent, name="splineGraph", up_axis="z"):
        """X軸方向の骨列を、3次カーブで制御する。

        Args:
            joints (Sequence[str | Node]): 根元から末端までの連続した骨列。
            controls (Sequence[str | Node]): CV位置を駆動する4〜32個のtransform。
            parent (str | Node): カーブとhandleを置くtransform。
            name (str): 一意なcontainer名。
            up_axis (str): ローカル上方向y/z。両端controlの同軸を上方向とする。

        Returns:
            SplineIK: 標準Spline IKグラフ。

        Note:
            既存骨の回転はIKソルバーに渡す。骨長は変更しない。
            入力骨・control・parentは所有しない。回転接続やキーのない骨を渡す。
        """
        joints, controls, parent = (
            [hlib.nodes.Node(n) for n in joints],
            [hlib.nodes.Node(n) for n in controls],
            hlib.nodes.Node(parent),
        )
        if len(joints) < 3 or not 4 <= len(controls) <= 32 or up_axis not in ("y", "z"):
            raise ValueError("Use 3+ joints, 4..32 controls and up_axis y/z")
        if cmds.objExists(name):
            raise ValueError("Graph name already exists")
        if len({n.uuid() for n in controls}) != len(controls):
            raise ValueError("Use distinct controls")
        for node in controls + [parent]:
            if node.type() != "transform" or any(
                node.fullName().startswith(j.fullName() + "|") for j in joints
            ):
                raise ValueError("Controls and parent must be transforms outside the IK chain")
        for i, joint in enumerate(joints):
            if joint.type() != "joint":
                raise ValueError("Expected joints")
            if i and [
                node.uuid()
                for node in [
                    hlib.getNode(value) for value in (cmds.listRelatives(joint, parent=True) or [])
                ]
            ] != [joints[i - 1].uuid()]:
                raise ValueError("Expected a continuous joint chain")
            if any(joint.plug("rotate" + a).source() is not None for a in "XYZ"):
                raise ValueError("Joint rotation already has an input")
        graph = cls(hlib.nodes.Container.create(name=name))
        points = [
            tuple(hlib.utils.units.distance_to_ui(v) for v in c.getTranslation(space=MSpace.kWorld))
            for c in controls
        ]
        curve = hlib.nodes.Node(hlib.createCurve(degree=3, point=points, name=name + "_curve"))
        [
            hlib.getNode(value)
            for value in (cmds.parent(curve.fullName(), parent.fullName(), relative=True) or [])
        ]
        shape = hlib.nodes.Node(
            [
                hlib.getNode(value)
                for value in (
                    cmds.listRelatives(curve.fullName(), shapes=True, fullPath=True) or []
                )
            ][0]
        )
        for index, control in enumerate(controls):
            matrix = hlib.nodes.Node.create(
                "multMatrix", name=name + "_cv{}Matrix".format(index), skipSelect=True
            )
            position = hlib.nodes.Node.create(
                "decomposeMatrix", name=name + "_cv{}Position".format(index), skipSelect=True
            )
            control.plug("worldMatrix[0]").connect(matrix.plug("matrixIn[0]"))
            curve.plug("worldInverseMatrix[0]").connect(matrix.plug("matrixIn[1]"))
            matrix.plug("matrixSum").connect(position.plug("inputMatrix"))
            position.plug("outputTranslate").connect(shape.plug("controlPoints[{}]".format(index)))
            graph.container.addMembers(matrix, position)
        handle_name, effector_name = hlib.createIkHandle(
            startJoint=joints[0].fullName(),
            endEffector=joints[-1].fullName(),
            solver="ikSplineSolver",
            curve=curve.fullName(),
            createCurve=False,
            parentCurve=False,
            rootOnCurve=True,
            name=name + "_ikh",
        )[:2]
        handle, effector = hlib.nodes.Node(handle_name), hlib.nodes.Node(effector_name)
        effector.rename(name + "_effector")
        [hlib.getNode(value) for value in (cmds.parent(handle.fullName(), parent.fullName()) or [])]
        handle.plug("dTwistControlEnable").set(True)
        handle.plug("dWorldUpType").set(4)
        handle.plug("dForwardAxis").set(0)
        handle.plug("dWorldUpAxis").set(0 if up_axis == "y" else 3)
        vector = (0, 1, 0) if up_axis == "y" else (0, 0, 1)
        for attr in ("dWorldUpVector", "dWorldUpVectorEnd"):
            handle.plug(attr).set(vector)
        controls[0].plug("worldMatrix[0]").connect(handle.plug("dWorldUpMatrix"))
        controls[-1].plug("worldMatrix[0]").connect(handle.plug("dWorldUpMatrixEnd"))
        for role, node in (("handle", handle), ("curve", curve), ("effector", effector)):
            graph.container.addAttribute(longName=role, attributeType="message")
            node.plug("message").connect(graph.container.plug(role))
            graph.container.addMembers(node)
        curve.plug("visibility").set(False)
        handle.plug("visibility").set(False)
        return graph

    @undo_transaction("hrig.SplineIK.set_enabled")
    def set_enabled(self, enabled):
        """停止時はカーブ入力を切断し、ソルバーを無効化する。

        Args:
            enabled (bool): 計算するか。
        """
        handle = self.member("handle")
        target = handle.plug("inCurve")
        if enabled:
            if target.source() is None:
                shape = hlib.nodes.Node(
                    [
                        hlib.getNode(value)
                        for value in (
                            cmds.listRelatives(
                                self.member("curve").fullName(), shapes=True, fullPath=True
                            )
                            or []
                        )
                    ][0]
                )
                shape.plug("worldSpace[0]").connect(target)
            handle.plug("nodeState").set(0)
            handle.plug("ikBlend").set(1)
        else:
            handle.plug("ikBlend").set(0)
            if target.source() is not None:
                target.source().disconnect(target)
            handle.plug("nodeState").set(2)
