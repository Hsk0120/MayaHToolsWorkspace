"""不均一なscaleを子へ伝えない「枝のjointと葉のjoint」の書き出し用骨格を、標準DGで作る。"""

import mlib
from mlib.decorator import undoTransaction

from mlrig.setups.twistDistribution import TwistDistribution


class LeafJoints(TwistDistribution):
    """入力の節ごとに、scale を持たない枝のjointと、scale だけを受け持つ葉のjointを作る標準DG。

    つぶし・伸ばし(squash & stretch)のように節を不均一に拡大縮小するリグを、親の scale を
    子へそのまま掛ける(segmentScaleCompensate の無い)ゲームエンジンなどへ書き出すための一般的な構成。
    枝のjointは入力の節の位置と回転だけを受け持って階層を作り、葉のjointは枝の子(階層の末端)に置いて
    その節の scale を受け持つ。スキンのウェイトを葉のjointへ付ければ、肘を太くしても前腕が太らない。
    """

    @classmethod
    @undoTransaction("mlrig.LeafJoints.create")
    def create(cls, sources, name="leafJoints", parent=None, shear=False):
        """入力の節ごとに枝と葉のjointを作り、入力のワールド行列へ追従させる。

        Args:
            sources (list[str | Node]): 入力の節(transformまたはjoint)。親子の関係は、各節のDAGの祖先のうち
                最も近い sources の節を親とする(無ければ ``parent`` の直下)。列の順は問わない。
            name (str): 一意なcontainer名。jointは ``<name>_branch<i>``・``<name>_leaf<i>`` になる。
            parent (str | Node | None): 枝の階層の根を置くtransform(書き出しの根)。Noneならワールド。
                scale を持たない(1,1,1)ことを前提とする。
            shear (bool): Trueなら葉のjointへ shear も渡す(入力のワールド行列に剪断があっても一致する)。
                既定のFalseは、剪断を表せない書き出し先に合わせて scale だけを渡す。

        Returns:
            LeafJoints: branch<i>・leaf<i>(message)、branchMatrix<i>(枝のローカル行列)、
            leafMatrix<i>(葉のローカル行列)の所有者。jointもcontainerのメンバーになる。

        Raises:
            ValueError: 引数が不正な場合、またはnameが既に存在する場合。

        Note:
            行ベクトル規約で、入力の節iのワールド行列を W_i、そこから scale と shear を除いた行列
            (``pickMatrix``、位置と回転だけ)を N_i とする。枝のローカル行列は B_i = N_i * N_p^-1
            (pは親の節。N_p^-1 は枝のjointの parentInverseMatrix で、根は ``parent`` の逆行列、ワールドなら
            単位行列)、葉のローカル行列は F_i = W_i * N_i^-1 (scale と shear だけが残る。N_i^-1 は葉の
            parentInverseMatrix)。それぞれを ``decomposeMatrix`` して、
            枝は translate・rotate、葉は scale(と shear)へ接続する。枝と葉のjointは jointOrient が0、
            segmentScaleCompensate がFalseなので、親の行列をそのまま掛ける書き出し先でも
            枝のワールド行列は N_i、葉のワールド行列は W_i(shear=Falseで剪断が無い場合)になり、
            枝は scale 1 のまま、ある節の scale は葉にしか現れない。
        """
        if mlib.objExists(name):
            raise ValueError("LeafJoints container already exists: " + name)
        if sources is None or isinstance(sources, str):
            raise ValueError("Expected a list of transforms for the sources")
        nodes = [mlib.nodes.Node(node) for node in sources]
        if not nodes or any(not isinstance(node, mlib.nodes.Transform) for node in nodes):
            raise ValueError("Expected one or more transforms for the sources")
        uuids = [node.getUuid() for node in nodes]
        if len(set(uuids)) != len(uuids):
            raise ValueError("The sources have the same transform more than once")
        root = None
        if parent is not None:
            root = mlib.nodes.Node(parent)
            if not isinstance(root, mlib.nodes.Transform):
                raise ValueError("Expected a transform for the parent")
            if root.getUuid() in uuids:
                raise ValueError("The parent must not be one of the sources")
        parents = []
        for node in nodes:
            found, ancestor = None, node.getParent()
            while ancestor is not None:
                if ancestor.getUuid() in uuids:
                    found = uuids.index(ancestor.getUuid())
                    break
                ancestor = ancestor.getParent()
            parents.append(found)

        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        flat = []
        for index, node in enumerate(nodes):
            # N_i: 入力のワールド行列から scale と shear を除いた、位置と回転だけの行列。
            pick = graph._node("pickMatrix", "flat" + str(index))
            node.getPlug("worldMatrix")[0].connectTo(pick.getPlug("inputMatrix"))
            pick.getPlug("useScale").set(False)
            pick.getPlug("useShear").set(False)
            flat.append(pick.getPlug("outputMatrix"))

        branches, leaves = [], []
        for index, node in enumerate(nodes):
            branch = mlib.createNode("joint", name="{}_branch{}".format(name, index), skipSelect=True)
            leaf = mlib.createNode("joint", name="{}_leaf{}".format(name, index), parent=branch,
                                   skipSelect=True)
            for joint in (branch, leaf):
                joint.getPlug("segmentScaleCompensate").set(False)
                owner.addMembers(joint)
            branches.append(branch)
            leaves.append(leaf)
        for index, branch in enumerate(branches):
            if parents[index] is not None:
                branch.setParent(branches[parents[index]])
            elif root is not None:
                branch.setParent(root)
            # 親子付けはワールドの姿勢を保つため jointOrient に親の回転を入れるので、0へ戻す
            # (位置と回転はこの後 translate・rotate へ接続する)。
            branch.getPlug("jointOrient").set((0.0, 0.0, 0.0))

        for index, node in enumerate(nodes):
            branch, leaf = branches[index], leaves[index]
            for label, joint in (("branch", branch), ("leaf", leaf)):
                owner.addAttr(longName=label + str(index), attributeType="message")
                joint.getPlug("message").connectTo(owner.getPlug(label + str(index)))
            # 枝: B_i = N_i * N_p^-1。枝のjointの parentInverseMatrix は親の枝(ワールド行列 N_p)・
            # parent・ワールドの逆行列なので、それを掛ける(自分の translate・rotate には依存しない)。
            local = graph._node("multMatrix", "branchLocal" + str(index))
            flat[index].connectTo(local.getPlug("matrixIn")[0])
            branch.getPlug("parentInverseMatrix")[0].connectTo(local.getPlug("matrixIn")[1])
            owner.addAttr(longName="branchMatrix" + str(index), dataType="matrix")
            local.getPlug("matrixSum").connectTo(owner.getPlug("branchMatrix" + str(index)))
            parts = graph._node("decomposeMatrix", "branchParts" + str(index))
            local.getPlug("matrixSum").connectTo(parts.getPlug("inputMatrix"))
            parts.getPlug("outputTranslate").connectTo(branch.getPlug("translate"))
            parts.getPlug("outputRotate").connectTo(branch.getPlug("rotate"))
            # 葉: F_i = W_i * N_i^-1(scale と shear だけが残る)。N_i^-1 は葉の parentInverseMatrix(枝の逆行列)。
            scale = graph._node("multMatrix", "leafLocal" + str(index))
            node.getPlug("worldMatrix")[0].connectTo(scale.getPlug("matrixIn")[0])
            leaf.getPlug("parentInverseMatrix")[0].connectTo(scale.getPlug("matrixIn")[1])
            owner.addAttr(longName="leafMatrix" + str(index), dataType="matrix")
            scale.getPlug("matrixSum").connectTo(owner.getPlug("leafMatrix" + str(index)))
            leafParts = graph._node("decomposeMatrix", "leafParts" + str(index))
            scale.getPlug("matrixSum").connectTo(leafParts.getPlug("inputMatrix"))
            leafParts.getPlug("outputScale").connectTo(leaf.getPlug("scale"))
            if shear:
                leafParts.getPlug("outputShear").connectTo(leaf.getPlug("shear"))
        return graph

    def getJoints(self):
        """作成した枝と葉のjointを返す。

        Returns:
            tuple[list[Node], list[Node]]: (枝のjointの列, 葉のjointの列)。入力の節と同じ順。
        """
        branches, leaves = [], []
        index = 0
        while self.container.hasAttr("branch" + str(index)):
            branches.append(self.container.getPlug("branch" + str(index)).getSource(skipConversionNodes=True).getNode())
            leaves.append(self.container.getPlug("leaf" + str(index)).getSource(skipConversionNodes=True).getNode())
            index += 1
        return branches, leaves
