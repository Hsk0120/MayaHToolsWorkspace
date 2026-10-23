"""標準行列ノードによる、姿勢を保持した参照空間の切替。"""

from maya import cmds

import json
import re

import mlib

from mlib.maths.matrix import Matrix
from mlib.decorator import undoTransaction


class SpaceSwitch:
    """専用transformのoffsetParentMatrixを参照空間へ追従させる。

    切替時は選択先のオフセットを更新する構成操作。時系列の空間切替キーや
    ブレンドではない。専用transformのTRSは恒等値のまま使用する。
    """

    def __init__(self, buffer):
        """保存済みの切替transformを参照する。

        Args:
            buffer (str | Node): createで初期化したtransform。
        """
        self.buffer = mlib.nodes.Node(buffer)
        if not self.buffer.hasAttr("spaceChoice"):
            raise ValueError("Not a space-switch buffer")

    @classmethod
    @undoTransaction("mlrig.SpaceSwitch.create")
    def create(cls, buffer):
        """恒等TRSのtransformへ選択ノードを追加する。

        Args:
            buffer (str | Node): 未接続のoffsetParentMatrixを持つ専用transform。

        Returns:
            SpaceSwitch: 空間登録前の切替オブジェクト。
        """
        buffer = mlib.nodes.Node(buffer)
        if buffer.getType() != "transform" or buffer.hasAttr("spaceChoice"):
            raise ValueError("Expected an unused transform")
        if buffer.getPlug('offsetParentMatrix').getSource(skipConversionNodes=False) is not None:
            raise ValueError("offsetParentMatrix is already connected")
        identity = Matrix()
        if any(abs(a - b) > 1e-8 for a, b in zip(buffer.getPlug("matrix").get(), identity)):
            raise ValueError("Space buffer must have identity local channels")
        buffer.addAttr(longName="spaceChoice", attributeType="message")
        buffer.addAttr(longName="spaceLabels", dataType="string")
        buffer.getPlug("spaceLabels").set("[]")
        choice = mlib.nodes.Node.create("choice", name=buffer.getName() + "_choice", skipSelect=True)
        choice.getPlug("message").connectTo(buffer.getPlug("spaceChoice"))
        return cls(buffer)

    def _choice(self):
        """保存された選択ノードを取得する。

        Returns:
            Node: choiceノード。
        """
        return self.buffer.getPlug('spaceChoice').getSource(skipConversionNodes=False).getNode()

    def labels(self):
        """登録された空間名を順序付きで取得する。

        Returns:
            tuple[str]: enumインデックス順の名前。
        """
        return tuple(json.loads(self.buffer.getPlug("spaceLabels").get()))

    def getCurrent(self):
        """現在適用されている空間名を取得する。

        Returns:
            str: 空間名。
        """
        return self.labels()[self._choice().getPlug("selector").get()]

    def getNodes(self):
        """所有する生成物を取得する。参照先transformは含めない。

        Returns:
            tuple[Node]: buffer、choice、空間ごとのmultMatrix。
        """
        choice = self._choice()
        return (self.buffer, choice) + tuple((choice.getPlug('input')[i].getSource(skipConversionNodes=False).getNode() for i in range(len(self.labels()))))

    def _validate_target(self, target):
        """自己・子孫・計算依存先への追従による循環を拒否する。

        Args:
            target (Node): 参照するtransform。
        """
        if not isinstance(target, mlib.nodes.Transform):
            raise ValueError("Space target must have a world matrix")
        path = target.getFullName()
        if path == self.buffer.getFullName() or path.startswith(self.buffer.getFullName() + "|"):
            raise ValueError("Space target cannot be the buffer or its descendant")
        pending, visited = [target], set()
        while pending:
            item = pending.pop()
            key = item.getUuid()
            if key in visited:
                continue
            visited.add(key)
            if item.mnode() == self.buffer.mnode():
                raise ValueError("Space target depends on the driven buffer")
            # DAG親子とDG入力の両方を辿る。所有参照のmessage接続は計算依存ではない。
            if isinstance(item, (mlib.nodes.Transform, mlib.nodes.Shape)):
                parents = [
                    mlib.getNode(value)
                    for value in (
                        cmds.listRelatives(item.getFullName(), parent=True, fullPath=True) or []
                    )
                ] or []
                pending.extend(mlib.nodes.Node(parent) for parent in parents)
            pairs = [
                mlib.getPlug(value)
                for value in (
                    cmds.listConnections(
                        item.getFullName(),
                        source=True,
                        destination=False,
                        plugs=True,
                        connections=True,
                    )
                    or []
                )
            ] or []
            for destination, source in zip(pairs[::2], pairs[1::2]):
                if mlib.getPlug(destination).getDataType() != "message":
                    pending.append(source.getNode())

    @staticmethod
    def _inverse(matrix):
        """ゼロ・極小スケールを拒否して参照空間の逆行列を返す。

        Args:
            matrix (Matrix): ワールド行列。

        Returns:
            Matrix: 逆行列。
        """
        # Mayaはscale=0をworldMatrix上で1e-12へ置換する版がある。
        tiny_axis = any(sum(matrix[i + j] ** 2 for j in range(3)) <= 1e-20 for i in (0, 4, 8))
        if matrix.isSingular() or tiny_axis:
            raise ValueError("Singular or near-zero scale in space matrix")
        return matrix.inverse()

    @undoTransaction("mlrig.SpaceSwitch.add")
    def add(self, label, target=None):
        """指定ノードまたはワールドを空間として追加する。

        Args:
            label (str): 重複しない英数字・アンダースコアの空間名。
            target (str | Node | None): 参照ノード。Noneならワールド。

        Returns:
            int: 新しい空間のインデックス。
        """
        labels = self.labels()
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", label) or label in labels:
            raise ValueError("Invalid or duplicate space label")
        target = mlib.nodes.Node(target) if target is not None else None
        if target is not None:
            self._validate_target(target)
        world = self.buffer.getPlug("worldMatrix")[0].get()
        reference = target.getPlug("worldMatrix")[0].get() if target else Matrix()
        reference = Matrix(reference)
        offset = Matrix(world) * self._inverse(reference)
        matrix = mlib.nodes.Node.create(
            "multMatrix", name=self.buffer.getName() + "_" + label + "_multMatrix", skipSelect=True
        )
        matrix.getPlug("matrixIn")[0].set(offset)
        if target is not None:
            target.getPlug("worldMatrix")[0].connectTo(matrix.getPlug("matrixIn")[1])
        else:
            matrix.getPlug("matrixIn")[1].set(Matrix())
        # buffer.parentInverseMatrixは自身のOPMを含むので使わず、実親を参照する。
        parent = [
            mlib.getNode(value)
            for value in (
                cmds.listRelatives(self.buffer.getFullName(), parent=True, fullPath=True) or []
            )
        ] or []
        if parent:
            mlib.nodes.Node(parent[0]).getPlug("worldInverseMatrix")[0].connectTo(
                matrix.getPlug("matrixIn")[2]
            )
        else:
            matrix.getPlug("matrixIn")[2].set(Matrix())
        choice = self._choice()
        matrix.getPlug("matrixSum").connectTo(choice.getPlug("input")[len(labels)])
        self.buffer.getPlug("spaceLabels").set(json.dumps(labels + (label,)))
        if not labels:
            choice.getPlug("output").connectTo(self.buffer.getPlug("offsetParentMatrix"))
        return len(labels)

    @undoTransaction("mlrig.SpaceSwitch.switch")
    def switch(self, label):
        """ワールド姿勢と子のローカルチャンネルを保持して空間を切り替える。

        Args:
            label (str): 登録済みの空間名。
        """
        index = self.labels().index(label)
        choice = self._choice()
        if choice.getPlug("selector").get() == index:
            return
        matrix = choice.getPlug('input')[index].getSource(skipConversionNodes=False).getNode()
        source = matrix.getPlug('matrixIn')[1].getSource(skipConversionNodes=False)
        if source is not None:
            self._validate_target(source.getNode())
        reference = Matrix(matrix.getPlug("matrixIn")[1].get())
        offset = Matrix(self.buffer.getPlug("worldMatrix")[0].get()) * self._inverse(reference)
        matrix.getPlug("matrixIn")[0].set(offset)
        choice.getPlug("selector").set(index)
