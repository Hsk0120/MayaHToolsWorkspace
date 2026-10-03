"""専用Transformバッファを単一入力の行列へ追従させる。"""

from maya import cmds
from pathlib import Path

import hlib
from hlib.maths import Matrix
from hlib.decorators.undo import undo_transaction


class MatrixFollow:
    """標準・C++・Bifrostの行列積で全成分を追従するセットアップ。

    parentConstraintの完全互換ではない。scale/shearも追従する。
    targetはローカル行列が恒等で、pivot/rotateAxisを持たない専用Transformとする。
    接続後のtargetのTRS編集・再親付け・instancingは対象外。
    jointOrient、複数入力の回転ブレンド、軸スキップは扱わない。
    BifrostはUndo無効の専用プロセス限定の検証用実装。
    """

    @staticmethod
    def _validate_dependencies(source, target):
        """入力依存を辿り、循環と複数DAGパスを構築前に拒否する。

        Args:
            source (Node): 入力Transform。
            target (Node): 出力バッファ。
        """
        pending, visited = [source, target.parentNode()], set()
        # target自体のインスタンスも確認する。親のインスタンスは探索で検出する。
        if len(cmds.listRelatives(target.fullName(), allParents=True) or []) > 1:
            raise ValueError("Instanced targets are not supported")
        while pending:
            item = pending.pop()
            if item is None or item.uuid() in visited:
                continue
            visited.add(item.uuid())
            if item.uuid() == target.uuid():
                raise ValueError("Source or parent depends on target")
            if isinstance(item, (hlib.nodes.Transform, hlib.nodes.Shape)):
                parents = cmds.listRelatives(item.fullName(), allParents=True, fullPath=True) or []
                if len(parents) > 1:
                    raise ValueError("Instanced hierarchy is not supported")
                pending.extend(hlib.getNode(parent) for parent in parents)
            pairs = (
                cmds.listConnections(
                    item.fullName(), source=True, destination=False, plugs=True, connections=True
                )
                or []
            )
            for destination, upstream in zip(pairs[::2], pairs[1::2]):
                if hlib.getAttr(destination, type=True) != "message":
                    pending.append(hlib.getPlug(upstream).node)

    @staticmethod
    @undo_transaction("hrig.MatrixFollow.create")
    def create(source, target, maintain_offset=True, name=None, backend="standard"):
        """バッファへワールド行列を親空間に変換して接続する。

        Args:
            source (Node | str): 入力Transform。
            target (Node | str): 未接続で恒等TRSの専用Transform。
            maintain_offset (bool): 構築時のワールド姿勢を保持する。
            name (str | None): 生成する計算ノードの名前。
            backend (str): standard、cpp、bifrost。追加プラグインは明示選択時のみロード。

        Returns:
            Node: 計算ノード参照。Bifrostの場合はgraphShapeで、そのDAG親も所有対象。

        Raises:
            ValueError: 対象が専用バッファの条件を満たさない場合。
            RuntimeError: 行列が特異、接続が循環、またはMayaが接続を拒否する場合。
        """
        if backend not in ("standard", "cpp", "bifrost"):
            raise ValueError("Unknown matrix backend: " + backend)
        source, target = hlib.getNode(source), hlib.getNode(target)
        if source.type() != "transform" or target.type() != "transform":
            raise ValueError("MatrixFollow requires transform buffers, not joints")
        if source.uuid() == target.uuid() or target.isAncestorOf(source):
            raise ValueError("Source must not depend on the target hierarchy")
        MatrixFollow._validate_dependencies(source, target)
        identity = Matrix()
        for attr in ("matrix", "offsetParentMatrix"):
            if any(abs(a - b) > 1e-9 for a, b in zip(target.plug(attr).get(), identity)):
                raise ValueError("Target must have identity local/offset matrices")
        for attr in (
            "translate",
            "rotate",
            "scale",
            "shear",
            "rotateAxis",
            "rotatePivot",
            "scalePivot",
            "rotatePivotTranslate",
            "scalePivotTranslate",
        ):
            plug = target.plug(attr)
            expected = (1, 1, 1) if attr == "scale" else (0, 0, 0)
            if any(abs(a - b) > 1e-9 for a, b in zip(plug.get(), expected)):
                raise ValueError("Target channels/pivots must be at their defaults")
            if plug.source() is not None or any(
                child.source() is not None for child in plug.children()
            ):
                raise ValueError("Target channels must have no incoming connections")
        if target.plug("offsetParentMatrix").source() is not None:
            raise ValueError("Target offsetParentMatrix is already connected")
        if target.isLocked() or target.plug("offsetParentMatrix").isLocked():
            raise ValueError("Target offsetParentMatrix must be writable")
        if (
            not target.plug("inheritsTransform").get()
            or target.plug("inheritsTransform").source() is not None
        ):
            raise ValueError("Target must inherit its parent transform")
        parent = target.parentNode()
        if parent is not None:
            parent_matrix = Matrix(parent.plug("worldMatrix[0]").get())
            if parent_matrix.isSingular() or any(
                sum(parent_matrix[i + j] ** 2 for j in range(3)) <= 1e-20 for i in (0, 4, 8)
            ):
                raise ValueError("Parent matrix must be invertible")
        source_matrix = Matrix(source.plug("worldMatrix[0]").get())
        if source_matrix.isSingular() or any(
            sum(source_matrix[i + j] ** 2 for j in range(3)) <= 1e-20 for i in (0, 4, 8)
        ):
            raise ValueError("Source matrix must be invertible")
        offset = (
            Matrix(target.plug("worldMatrix[0]").get()) * source_matrix.inverse()
            if maintain_offset
            else identity
        )
        name = name or target.name() + "_followMatrix"
        return MatrixFollow._build(source, target, parent, offset, name, backend)

    @staticmethod
    def _build(source, target, parent, offset, name, backend):
        """検証済みの入力から計算ノードと接続を組み立てる。

        Args:
            source (Node): 入力Transform。
            target (Node): 出力バッファ。
            parent (Node | None): 出力の実親。
            offset (Matrix): 保持する相対行列。
            name (str): 計算ノード名。
            backend (str): 検証済みのバックエンド名。

        Returns:
            Node: 計算ノード。通常は検証・Undo付きcreateから呼び出す。
        """
        identity = Matrix()
        if backend == "standard":
            graph = hlib.createNode("multMatrix", name=name, skipSelect=True)
            inputs, output = ("matrixIn[0]", "matrixIn[1]", "matrixIn[2]"), "matrixSum"
        else:
            inputs, output = ("offset", "sourceWorld", "parentInverse"), "outputMatrix"
            if backend == "cpp":
                version = str(cmds.about(version=True)).split()[0]
                plugin = (
                    Path(__file__).parents[1]
                    / "release/plug-ins/windows"
                    / version
                    / "hrigNodes.mll"
                )
                hlib.environment.Plugin(str(plugin)).ensure_loaded()
                graph = hlib.createNode("hrigMatrixFollow", name=name, skipSelect=True)
            else:
                from .bifrostMatrixFollow import BifrostMatrixFollow

                graph = BifrostMatrixFollow.create(name).node
        graph.plug(inputs[0]).set(offset)
        source.plug("worldMatrix[0]").connect(graph.plug(inputs[1]))
        graph.plug(inputs[2]).set(identity)
        if parent is not None:
            parent.plug("worldInverseMatrix[0]").connect(graph.plug(inputs[2]))
        graph.plug(output).connect(target.plug("offsetParentMatrix"))
        return graph
