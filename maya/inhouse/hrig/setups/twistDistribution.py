"""二つの参照姿勢から軸ツイストを抽出し、標準ノードで分配する。"""

from maya import cmds

import hlib

from hlib.decorators.undo import undoTransaction


class TwistDistribution:
    """始点空間で位置と軸回転を補間する、container所有の標準DG。"""

    def __init__(self, container):
        """作成済みの計算containerを保持する。

        Args:
            container (str | Node): createで生成したノード。
        """
        self.container = hlib.nodes.Container(container)

    def _node(self, kind, suffix):
        """演算ノードを生成してcontainerへ登録する。

        Args:
            kind (str): 標準ノード型。
            suffix (str): 用途名。

        Returns:
            Node: 生成ノード。
        """
        node = hlib.nodes.Node.create(
            kind, name=self.container.name() + "_" + suffix, skipSelect=True
        )
        self.container.addMembers(node)
        return node

    @classmethod
    @undoTransaction("hrig.TwistDistribution.create")
    def create(cls, start, end, name="twist", axis="x"):
        """相対Quaternionの軸成分から純粋なツイストを抽出する。

        Args:
            start (str | Node): 始点transform。
            end (str | Node): 終点transform。
            name (str): 計算container名。
            axis (str): 始点ローカルの長手軸。x/y/z。

        Returns:
            TwistDistribution: sampleで補間行列を生成できる計算オブジェクト。

        Note:
            最短回転の範囲で扱い、複数回転の蓄積は行わない。
            軸に直交する180度曲げではツイストが不定となるため恒等回転にする。
        """
        if axis not in ("x", "y", "z"):
            raise ValueError("axis must be x, y or z")
        start, end = hlib.nodes.Node(start), hlib.nodes.Node(end)
        if start.uuid() == end.uuid() or any(
            not isinstance(n, hlib.nodes.Transform) for n in (start, end)
        ):
            raise ValueError("Expected two different transforms")
        if cmds.objExists(name):
            raise ValueError("Twist container already exists: " + name)
        graph = cls(hlib.nodes.Container.create(name=name))
        owner = graph.container
        owner.addAttr(longName="twistMatrix", dataType="matrix")
        owner.addAttr(longName="relativeDecompose", attributeType="message")
        relative = graph._node("multMatrix", "relative")
        parents = [
            hlib.getNode(value)
            for value in (cmds.listRelatives(end.fullName(), parent=True, fullPath=True) or [])
        ] or []
        if [node.uuid() for node in parents] == [start.uuid()]:
            # 隣接骨ならワールド行列を介さず、OPMを含む実ローカル行列を使う。
            end.plug("matrix").connectTo(relative.plug("matrixIn[0]"))
            end.plug("offsetParentMatrix").connectTo(relative.plug("matrixIn[1]"))
        else:
            end.plug("worldMatrix[0]").connectTo(relative.plug("matrixIn[0]"))
            start.plug("worldInverseMatrix[0]").connectTo(relative.plug("matrixIn[1]"))
        decompose = graph._node("decomposeMatrix", "decompose")
        relative.plug("matrixSum").connectTo(decompose.plug("inputMatrix"))
        decompose.plug("message").connectTo(owner.plug("relativeDecompose"))
        normalize = graph._node("multiplyDivide", "normalize")
        normalize.plug("operation").set(2)
        norm = graph._node("vectorProduct", "norm")
        norm.plug("operation").set(1)
        for source, dest in (("outputQuat" + axis.upper(), "X"), ("outputQuatW", "Y")):
            for operand in ("input1", "input2"):
                decompose.plug(source).connectTo(norm.plug(operand + dest))
        safe = graph._node("condition", "safe")
        safe.plug("operation").set(2)
        norm.plug("outputX").connectTo(safe.plug("firstTerm"))
        safe.plug("secondTerm").set(1e-12)
        decompose.plug("outputQuat" + axis.upper()).connectTo(safe.plug("colorIfTrueR"))
        decompose.plug("outputQuatW").connectTo(safe.plug("colorIfTrueG"))
        norm.plug("outputX").connectTo(safe.plug("colorIfTrueB"))
        safe.plug("colorIfFalseR").set(0)
        safe.plug("colorIfFalseG").set(1)
        safe.plug("colorIfFalseB").set(1)
        safe.plug("outColorR").connectTo(normalize.plug("input1X"))
        safe.plug("outColorG").connectTo(normalize.plug("input1Y"))
        magnitude = graph._node("multiplyDivide", "magnitude")
        magnitude.plug("operation").set(3)
        magnitude.plug("input1X").set(1)
        magnitude.plug("input2X").set(0.5)
        safe.plug("outColorB").connectTo(magnitude.plug("input1X"))
        for axis_name in ("X", "Y"):
            magnitude.plug("outputX").connectTo(normalize.plug("input2" + axis_name))
        compose = graph._node("composeMatrix", "twist")
        compose.plug("useEulerRotation").set(False)
        normalize.plug("outputX").connectTo(compose.plug("inputQuat" + axis.upper()))
        normalize.plug("outputY").connectTo(compose.plug("inputQuatW"))
        compose.plug("outputMatrix").connectTo(owner.plug("twistMatrix"))
        return graph

    @undoTransaction("hrig.TwistDistribution.sample")
    def sample(self, fraction, name):
        """位置とツイストを同じ割合で補間した始点空間の行列を作る。

        Args:
            fraction (float): 0から1の補間率。
            name (str): container内で一意な用途名。

        Returns:
            Plug: multMatrix.matrixSum。所有ノードはcontainerと共に削除される。
        """
        if not 0 <= fraction <= 1:
            raise ValueError("fraction must be between zero and one")
        blend = self._node("blendMatrix", name + "_rotation")
        self.container.plug("twistMatrix").connectTo(blend.plug("target[0].targetMatrix"))
        blend.plug("target[0].weight").set(fraction)
        # Maya 2022はbool、2025以降は連続ウェイトで成分を選択する。
        attrs = (
            ("translateWeight", "scaleWeight", "shearWeight")
            if blend.hasAttr("target[0].translateWeight")
            else ("useTranslate", "useScale", "useShear")
        )
        for attr in attrs:
            blend.plug("target[0]." + attr).set(0)
        position = self._node("multiplyDivide", name + "_position")
        decompose = self.container.plug("relativeDecompose").sourceWithConversion().node()
        decompose.plug("outputTranslate").connectTo(position.plug("input1"))
        position.plug("input2").set((fraction, fraction, fraction))
        translate = self._node("composeMatrix", name + "_translate")
        position.plug("output").connectTo(translate.plug("inputTranslate"))
        result = self._node("multMatrix", name + "_matrix")
        blend.plug("outputMatrix").connectTo(result.plug("matrixIn[0]"))
        translate.plug("outputMatrix").connectTo(result.plug("matrixIn[1]"))
        return result.plug("matrixSum")
