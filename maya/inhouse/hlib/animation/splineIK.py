"""標準Spline IKと、コントロールからカーブへの接続を生成する。"""

from maya import cmds

from ..nodes.node import Node
from ..decorators.undo import undo_transaction


class SplineIK:
    """既存の骨とコントロールを入力とする、標準ノードの計算グラフ。"""

    def __init__(self, container):
        """保存済みグラフを参照する。

        Args:
            container (str | Node): 所有container。
        """
        self.container = Node(container)

    def member(self, name):
        """messageから構成ノードを取得する。

        Args:
            name (str): handle、curve、effector。

        Returns:
            Node: 参照先。
        """
        return self.container.plug(name).source().node

    @classmethod
    @undo_transaction("hlib.SplineIK.create")
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
            [Node(n) for n in joints],
            [Node(n) for n in controls],
            Node(parent),
        )
        if len(joints) < 3 or not 4 <= len(controls) <= 32 or up_axis not in ("y", "z"):
            raise ValueError("Use 3+ joints, 4..32 controls and up_axis y/z")
        if cmds.objExists(name):
            raise ValueError("Graph name already exists")
        if len({n.uuid() for n in controls}) != len(controls):
            raise ValueError("Use distinct controls")
        for node in controls + [parent]:
            if cmds.nodeType(node.full_name()) != "transform" or any(
                node.full_name().startswith(j.full_name() + "|") for j in joints
            ):
                raise ValueError("Controls and parent must be transforms outside the IK chain")
        for i, joint in enumerate(joints):
            if cmds.nodeType(joint.full_name()) != "joint":
                raise ValueError("Expected joints")
            if i and (cmds.listRelatives(joint.full_name(), parent=True, fullPath=True) or []) != [
                joints[i - 1].full_name()
            ]:
                raise ValueError("Expected a continuous joint chain")
            if any(joint.plug("rotate" + a).source() is not None for a in "XYZ"):
                raise ValueError("Joint rotation already has an input")
        graph = cls(cmds.container(name=name))
        points = [
            cmds.xform(c.full_name(), query=True, worldSpace=True, translation=True)
            for c in controls
        ]
        curve = Node(cmds.curve(degree=3, point=points, name=name + "_curve"))
        cmds.parent(curve.full_name(), parent.full_name(), relative=True)
        shape = Node(cmds.listRelatives(curve.full_name(), shapes=True, fullPath=True)[0])
        for index, control in enumerate(controls):
            matrix = Node.create(
                "multMatrix", name=name + "_cv{}Matrix".format(index), skipSelect=True
            )
            position = Node.create(
                "decomposeMatrix", name=name + "_cv{}Position".format(index), skipSelect=True
            )
            control.plug("worldMatrix[0]").connect(matrix.plug("matrixIn[0]"))
            curve.plug("worldInverseMatrix[0]").connect(matrix.plug("matrixIn[1]"))
            matrix.plug("matrixSum").connect(position.plug("inputMatrix"))
            position.plug("outputTranslate").connect(shape.plug("controlPoints[{}]".format(index)))
            cmds.container(
                graph.container.full_name(),
                edit=True,
                addNode=[matrix.full_name(), position.full_name()],
            )
        handle_name, effector_name = cmds.ikHandle(
            startJoint=joints[0].full_name(),
            endEffector=joints[-1].full_name(),
            solver="ikSplineSolver",
            curve=curve.full_name(),
            createCurve=False,
            parentCurve=False,
            rootOnCurve=True,
            name=name + "_ikh",
        )[:2]
        handle, effector = Node(handle_name), Node(effector_name)
        effector.rename(name + "_effector")
        cmds.parent(handle.full_name(), parent.full_name())
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
            graph.container.add_attr(long_name=role, attribute_type="message")
            node.plug("message").connect(graph.container.plug(role))
            cmds.container(graph.container.full_name(), edit=True, addNode=node.full_name())
        curve.plug("visibility").set(False)
        handle.plug("visibility").set(False)
        return graph

    @undo_transaction("hlib.SplineIK.set_enabled")
    def set_enabled(self, enabled):
        """停止時はカーブ入力を切断し、ソルバーを無効化する。

        Args:
            enabled (bool): 計算するか。
        """
        handle = self.member("handle")
        target = handle.plug("inCurve")
        if enabled:
            if target.source() is None:
                shape = Node(
                    cmds.listRelatives(
                        self.member("curve").full_name(), shapes=True, fullPath=True
                    )[0]
                )
                shape.plug("worldSpace[0]").connect(target)
            handle.plug("nodeState").set(0)
            handle.plug("ikBlend").set(1)
        else:
            handle.plug("ikBlend").set(0)
            if target.source() is not None:
                target.source().disconnect(target)
            handle.plug("nodeState").set(2)
