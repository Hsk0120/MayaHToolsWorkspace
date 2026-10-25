"""変形するメッシュの表面に貼り付いて動くコントロール(スティッキーコントロール)の標準DGを構築する。"""

import mlib
from mlib.decorator import undoTransaction
from mlib.maths import Matrix

from mlrig.setups.twistDistribution import TwistDistribution


class StickyControl(TwistDistribution):
    """コントロールを、変形したメッシュの表面の最も近い点に追従させる仕組み(Maya標準の ``proximityPin``)。

    生成時のコントロールのワールド行列 ``W0`` を、メッシュの元の形(変形前)に対する位置として ``proximityPin`` へ渡し、
    変形後の形で同じ場所に貼り付いた行列 ``matrix = pin · メッシュのworldMatrix`` を求める
    (``offsetTranslation`` ・ ``offsetOrientation`` を1にして、表面からの離れ・向きの差を保つ)。
    ``connect=True`` ならコントロールの ``offsetParentMatrix`` を ``L0^-1 · matrix · 親のworldInverseMatrix``
    (``L0`` は生成時のコントロールのローカル行列)にして、コントロール自体の移動・回転は表面の上での相対的な操作にする。
    メッシュが変形していなければ生成時の姿勢と一致し、跳ねない。
    """

    @classmethod
    @undoTransaction("mlrig.StickyControl.create")
    def create(cls, mesh, control, name="stickyControl", original=None, geometry=None, connect=True):
        """コントロールをメッシュの表面に貼り付けるDGを生成する。

        Args:
            mesh (str | Transform): 変形するメッシュのtransform(変形後の形を持つメッシュのシェイプの親)。
                空間はこのtransformのworldMatrixで扱う。
            control (str | Transform): 貼り付けるコントロールのtransform。生成時の位置で表面の場所を決める。
            name (str): 一意なcontainer名。
            original (str | Node | None): 変形前の形のメッシュのシェイプ。Noneなら mesh の中間シェイプ
                (デフォーマーを付けたときにMayaが作る ``<名前>ShapeOrig`` など)のうち最初のもの。
            geometry (str | Plug | None): 追従する変形後の形のplug(``skinCluster1.outputGeometry[0]`` など、
                メッシュのオブジェクト空間)。Noneなら mesh の変形後のシェイプの ``outMesh`` 。
                コントロール自身が動かすデフォーマーより前の段の出力を渡すと、二重の変形を避けられる。
            connect (bool): Trueならコントロールの ``offsetParentMatrix`` へ接続する。

        Returns:
            StickyControl: 出力の所有者。container に出力 ``matrix`` (表面に貼り付いたワールド行列)と、
                ``offsetParentMatrix`` (コントロールの ``offsetParentMatrix`` へ繋ぐ行列)を持つ。

        Raises:
            ValueError: mesh・control・originalが不正な場合、変形後/変形前のメッシュが見つからない場合、
                geometryがメッシュのplugでない場合、またはnameが既に存在する場合。

        Note:
            ``proximityPin`` の入力はメッシュのオブジェクト空間なので、 ``inputMatrix = W0 · M0^-1``
            (``M0`` は生成時のメッシュのworldMatrix)を定数として渡し、出力に ``D^-1`` (形のデータが持つ変換行列の逆、
            生成時の出力から求める定数)とメッシュの現在のworldMatrixを掛ける。
            コントロールの親の ``worldInverseMatrix`` は接続するので、親を動かしても貼り付いた位置は保たれる。
        """
        if mlib.ls(name):
            raise ValueError("StickyControl container already exists: " + name)
        mesh = mlib.nodes.Node(mesh)
        control = mlib.nodes.Node(control)
        if not isinstance(mesh, mlib.nodes.Transform):
            raise ValueError("Expected a transform for the mesh: " + str(mesh))
        if not isinstance(control, mlib.nodes.Transform):
            raise ValueError("Expected a transform for the control: " + str(control))
        if mesh.getUuid() == control.getUuid():
            raise ValueError("The mesh and the control must be different nodes")
        shapes = [shape for shape in mesh.getShapes(intermediates=True) if shape.getType() == "mesh"]
        deformed = [shape for shape in shapes if not shape.getPlug("intermediateObject").get()]
        if geometry is None:
            if not deformed:
                raise ValueError("No deformed mesh shape under: " + str(mesh))
            geometry = deformed[0].getPlug("outMesh")
        else:
            try:
                geometry = mlib.getPlug(str(geometry))
            except Exception:
                raise ValueError("geometry must be an existing mesh output plug: " + str(geometry))
        if original is None:
            rests = [shape for shape in shapes if shape.getPlug("intermediateObject").get()]
            if not rests:
                raise ValueError("No intermediate (original) mesh shape under {}; pass original".format(mesh))
            original = rests[0]
        else:
            original = mlib.nodes.Node(original)
            if isinstance(original, mlib.nodes.Transform):
                found = [shape for shape in original.getShapes(intermediates=True) if shape.getType() == "mesh"]
                if not found:
                    raise ValueError("No mesh shape under the original: " + str(original))
                original = found[0]
            if original.getType() != "mesh":
                raise ValueError("Expected a mesh for the original: " + str(original))

        graph = cls(mlib.nodes.Container.create(name=name))
        owner = graph.container
        for attribute in ("matrix", "offsetParentMatrix"):
            owner.addAttr(longName=attribute, dataType="matrix")

        restWorld = Matrix(control.getPlug("worldMatrix")[0].get())
        restMesh = Matrix(mesh.getPlug("worldMatrix")[0].get())
        pin = graph._node("proximityPin", "pin")
        original.getPlug("outMesh").connectTo(pin.getPlug("originalGeometry"))
        geometry.connectTo(pin.getPlug("deformedGeometry"))
        pin.getPlug("offsetTranslation").set(1.0)
        pin.getPlug("offsetOrientation").set(1.0)
        inputMatrix = restWorld * restMesh.inverse()
        pin.getPlug("inputMatrix")[0].set(inputMatrix)
        # デフォーマーの outputGeometry のように、形のデータ自体が変換行列 D を持つ場合、proximityPin の出力は
        # オブジェクト空間の結果に D を掛けたものになる(outMesh では D は単位行列)。生成時は出力が入力と一致するはずなので、
        # D = input^-1 · output を求めて打ち消し、メッシュの現在のworldMatrixを掛ける。
        data = inputMatrix.inverse() * Matrix(pin.getPlug("outputMatrix")[0].get())
        world = graph._node("multMatrix", "world")
        pin.getPlug("outputMatrix")[0].connectTo(world.getPlug("matrixIn")[0])
        world.getPlug("matrixIn")[1].set(data.inverse())
        mesh.getPlug("worldMatrix")[0].connectTo(world.getPlug("matrixIn")[2])
        world.getPlug("matrixSum").connectTo(owner.getPlug("matrix"))

        # offsetParentMatrix = L0^-1 · matrix · 親のworldInverseMatrix
        local = Matrix(control.getPlug("matrix").get())
        offset = graph._node("multMatrix", "offset")
        offset.getPlug("matrixIn")[0].set(local.inverse())
        owner.getPlug("matrix").connectTo(offset.getPlug("matrixIn")[1])
        above = control.getParent()
        if above is not None:
            above.getPlug("worldInverseMatrix")[0].connectTo(offset.getPlug("matrixIn")[2])
        offset.getPlug("matrixSum").connectTo(owner.getPlug("offsetParentMatrix"))
        if connect:
            owner.getPlug("offsetParentMatrix").connectTo(control.getPlug("offsetParentMatrix"))
        return graph
