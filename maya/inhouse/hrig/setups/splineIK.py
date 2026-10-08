"""標準Spline IKと、コントロールからカーブへの接続を生成する。"""
from hlib.maths import MSpace

from maya import cmds

import hlib

from hlib.decorator import undoTransaction


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
        return self.container.getPlug(name).getSourceWithConversion().getNode()

    @classmethod
    @undoTransaction("hrig.SplineIK.create")
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
        if len({n.getUuid() for n in controls}) != len(controls):
            raise ValueError("Use distinct controls")
        for node in controls + [parent]:
            if node.getType() != "transform" or any(
                node.getFullName().startswith(j.getFullName() + "|") for j in joints
            ):
                raise ValueError("Controls and parent must be transforms outside the IK chain")
        for i, joint in enumerate(joints):
            if joint.getType() != "joint":
                raise ValueError("Expected joints")
            if i and [
                node.getUuid()
                for node in [
                    hlib.getNode(value) for value in (cmds.listRelatives(joint, parent=True) or [])
                ]
            ] != [joints[i - 1].getUuid()]:
                raise ValueError("Expected a continuous joint chain")
            if any(joint.getPlug("rotate" + a).getSourceWithConversion() is not None for a in "XYZ"):
                raise ValueError("Joint rotation already has an input")
        graph = cls(hlib.nodes.Container.create(name=name))
        points = [
            tuple(hlib.common.units.distanceToUi(v) for v in c.getTranslation(ws=True, at=4))
            for c in controls
        ]
        curve = hlib.nodes.Node(hlib.createCurve(degree=3, point=points, name=name + "_curve"))
        [
            hlib.getNode(value)
            for value in (cmds.parent(curve.getFullName(), parent.getFullName(), relative=True) or [])
        ]
        shape = hlib.nodes.Node(
            [
                hlib.getNode(value)
                for value in (
                    cmds.listRelatives(curve.getFullName(), shapes=True, fullPath=True) or []
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
            control.getPlug("worldMatrix")[0].connectTo(matrix.getPlug("matrixIn")[0])
            curve.getPlug("worldInverseMatrix")[0].connectTo(matrix.getPlug("matrixIn")[1])
            matrix.getPlug("matrixSum").connectTo(position.getPlug("inputMatrix"))
            position.getPlug("outputTranslate").connectTo(shape.getPlug("controlPoints")[index])
            graph.container.addMembers(matrix, position)
        handle_name, effector_name = hlib.createIkHandle(
            startJoint=joints[0].getFullName(),
            endEffector=joints[-1].getFullName(),
            solver="ikSplineSolver",
            curve=curve.getFullName(),
            createCurve=False,
            parentCurve=False,
            rootOnCurve=True,
            name=name + "_ikh",
        )[:2]
        handle, effector = hlib.nodes.Node(handle_name), hlib.nodes.Node(effector_name)
        effector.rename(name + "_effector")
        [hlib.getNode(value) for value in (cmds.parent(handle.getFullName(), parent.getFullName()) or [])]
        handle.getPlug("dTwistControlEnable").set(True)
        handle.getPlug("dWorldUpType").set(4)
        handle.getPlug("dForwardAxis").set(0)
        handle.getPlug("dWorldUpAxis").set(0 if up_axis == "y" else 3)
        vector = (0, 1, 0) if up_axis == "y" else (0, 0, 1)
        for attr in ("dWorldUpVector", "dWorldUpVectorEnd"):
            handle.getPlug(attr).set(vector)
        controls[0].getPlug("worldMatrix")[0].connectTo(handle.getPlug("dWorldUpMatrix"))
        controls[-1].getPlug("worldMatrix")[0].connectTo(handle.getPlug("dWorldUpMatrixEnd"))
        for role, node in (("handle", handle), ("curve", curve), ("effector", effector)):
            graph.container.addAttr(longName=role, attributeType="message")
            node.getPlug("message").connectTo(graph.container.getPlug(role))
            graph.container.addMembers(node)
        curve.getPlug("visibility").set(False)
        handle.getPlug("visibility").set(False)
        return graph

    @undoTransaction("hrig.SplineIK.set_enabled")
    def set_enabled(self, enabled):
        """停止時はカーブ入力を切断し、ソルバーを無効化する。

        Args:
            enabled (bool): 計算するか。
        """
        handle = self.member("handle")
        target = handle.getPlug("inCurve")
        if enabled:
            if target.getSourceWithConversion() is None:
                shape = hlib.nodes.Node(
                    [
                        hlib.getNode(value)
                        for value in (
                            cmds.listRelatives(
                                self.member("curve").getFullName(), shapes=True, fullPath=True
                            )
                            or []
                        )
                    ][0]
                )
                shape.getPlug("worldSpace")[0].connectTo(target)
            handle.getPlug("nodeState").set(0)
            handle.getPlug("ikBlend").set(1)
        else:
            handle.getPlug("ikBlend").set(0)
            if target.getSourceWithConversion() is not None:
                target.disconnect(target.getSourceWithConversion())
            handle.getPlug("nodeState").set(2)
