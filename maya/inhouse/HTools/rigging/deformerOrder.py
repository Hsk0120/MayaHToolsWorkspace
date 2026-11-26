"""選択したシェイプのデフォーマーを出力側から並べ、隣接する二つを入れ替える。"""

import maya.cmds as cmds


def history(shape):
    """指定シェイプの履歴からデフォーマーを出力側から順に取得する。"""
    return [node for node in cmds.listHistory(shape, pruneDagObjects=True) or []
            if cmds.objectType(node, isAType="geometryFilter")]


def _restriction(stack):
    """履歴が複数経路や別形状へ影響する場合に理由を返す。"""
    for node in stack:
        geometry = cmds.deformer(node, query=True, geometry=True) or []
        if len(geometry) != 1:
            return "Cannot reorder a shared deformer: " + node
        indices = cmds.getAttr(node + ".outputGeometry", multiIndices=True) or []
        for index in indices:
            output = "{}.outputGeometry[{}]".format(node, index)
            destinations = cmds.listConnections(output, source=False, destination=True, plugs=True) or []
            if len(destinations) > 1:
                return "Cannot reorder a branched geometry output: " + output
        if cmds.nodeType(node) == "blendShape":
            # MayaのParallelは入力ターゲットに各枝のジオメトリを接続する。
            # 名前は変更できるため、ターゲットの実接続で判定する。
            inputs = cmds.listConnections(node + ".inputTarget", source=True, destination=False,
                                          connections=True, plugs=True) or []
            if any(plug.endswith(".inputGeomTarget") for plug in inputs[::2]):
                return "Cannot reorder across live blend shape target geometry: " + node
    return ""


def swap(shape, first, second):
    """同一形状に作用する隣接デフォーマーの順を変更する。"""
    stack = history(shape)
    if first not in stack or second not in stack or abs(stack.index(first) - stack.index(second)) != 1:
        raise ValueError("Choose two adjacent deformers in the same shape history.")
    restriction = _restriction(stack)
    if restriction:
        raise ValueError(restriction)
    later, earlier = sorted((first, second), key=stack.index)
    cmds.reorderDeformers(earlier, later, shape)


def run():
    """選択モデルの履歴を表示する。"""
    selected = cmds.ls(selection=True, objectsOnly=True, long=True) or []
    shapes = cmds.ls(selected, dag=True, shapes=True, noIntermediate=True, long=True) if selected else []
    if len(shapes or []) != 1:
        raise ValueError("Select one deformed shape.")
    shape = shapes[0]
    window = "HToolsDeformerOrder"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="Deformer Order")
    cmds.columnLayout(adjustableColumn=True)
    cmds.text(label=shape)
    listing = cmds.textScrollList(allowMultiSelection=True)
    status = cmds.text(label="")

    def refresh(*_):
        cmds.textScrollList(listing, edit=True, removeAll=True)
        stack = history(shape)
        for node in stack:
            cmds.textScrollList(listing, edit=True, append=node)
        reason = _restriction(stack)
        cmds.text(status, edit=True, label=reason)
        cmds.button(swap_button, edit=True, enable=not reason and len(stack) >= 2)

    def apply(*_):
        pair = cmds.textScrollList(listing, query=True, selectItem=True) or []
        if len(pair) != 2:
            raise ValueError("Select two adjacent deformers.")
        swap(shape, *pair)
        refresh()

    swap_button = cmds.button(label="Swap selected pair", command=apply)
    cmds.button(label="Refresh", command=refresh)
    refresh()
    cmds.showWindow(window)


if __name__ == "__main__":
    run()
