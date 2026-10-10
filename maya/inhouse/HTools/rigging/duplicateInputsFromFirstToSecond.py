"""選択2ノード間で入力接続を複製する簡易ツール。"""

import maya.cmds as cmds


def duplicate_all_inputs_from_first_to_second(source=None, target=None):
    """選択ノード [source, target]
    source に入っている全入力コネクション(srcPlug -> source.attr) を
    target の同名 attr にも接続する。
    source 側の接続は保持、target 側は force しない。

    source・target のどちらかを省略した場合は、選択の1つ目を source、2つ目を target にする。
    target 側が同じ接続済みならスキップ、ロック・既存の別入力・同名アトリビュートなしは失敗として数える。
    全接続を1回のUndoで戻せる。

    Args:
        source: 接続・変換・探索の元または先となる対象。
        target: 接続・変換・探索の元または先となる対象。
    """

    if source is None or target is None:
        sel = cmds.ls(sl=True, long=True) or []
        if len(sel) < 2:
            raise RuntimeError("Select two nodes (first = source, second = destination).")
        source, target = sel[0], sel[1]

    # source の「入力」コネクションを (source.attr, srcPlug) ペアで取得
    pairs = cmds.listConnections(
        source,
        source=True,
        destination=False,
        plugs=True,
        connections=True
    ) or []

    if not pairs:
        cmds.warning("No incoming connections found on the source node.")
        return

    connected = 0
    skipped = 0
    failed = 0

    cmds.undoInfo(openChunk=True, chunkName="duplicateInputsFromFirstToSecond")
    try:
        for i in range(0, len(pairs), 2):
            # source 側の入力先属性名を target 側の同名属性へマッピングする。
            dst_plug = target + "." + pairs[i].split(".", 1)[1]  # target.attr
            src_plug = pairs[i + 1]  # upstream plug

            try:
                if cmds.isConnected(src_plug, dst_plug):
                    skipped += 1
                    continue
                if cmds.getAttr(dst_plug, lock=True):
                    raise RuntimeError("Attribute is locked: " + dst_plug)
                # force しないため、別の入力が既にある場合は Maya がエラーにする。
                cmds.connectAttr(src_plug, dst_plug, force=False)
                connected += 1
            except Exception as e:
                failed += 1
                cmds.warning("Connection failed: {} -> {} ({})".format(src_plug, dst_plug, e))
    finally:
        cmds.undoInfo(closeChunk=True)

    cmds.inViewMessage(
        amg=f"Inputs duplicated: connected <hl>{connected}</hl> / "
            f"skipped <hl>{skipped}</hl> / failed <hl>{failed}</hl>",
        pos="topCenter",
        fade=True
    )


if __name__ == "__main__":
    # 実行
    duplicate_all_inputs_from_first_to_second()
