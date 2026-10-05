"""選択2ノード間で入力接続を複製する簡易ツール。"""

import maya.cmds as cmds
import hlib


def duplicate_all_inputs_from_first_to_second(source=None, target=None):
    """選択ノード [source, target]
    source に入っている全入力コネクション(srcPlug -> source.attr) を
    target の同名 attr にも接続する。
    source 側の接続は保持、target 側は force しない。

    Args:
        source: 接続・変換・探索の元または先となる対象。
        target: 接続・変換・探索の元または先となる対象。
    """

    sel = cmds.ls(sl=True, long=True) or []
    if source is None or target is None:
        if len(sel) < 2:
            raise RuntimeError("Select two nodes (first = source, second = destination).")
        source, target = sel[0], sel[1]

    # source の「入力」コネクションを (srcPlug, dstPlug) ペアで取得
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

    for i in range(0, len(pairs), 2):
        # source 側の入力先属性名を target 側の同名属性へマッピングする。
        print(sel[1])
        print(pairs[i].split("."))
        dst_plug = sel[1] + "." + pairs[i].split(".")[1]      # upstream plug
        src_plug = pairs[i + 1]  # source.attr

        print("src_plug:", src_plug)
        print("dst_plug:", dst_plug)


        hlib.getPlug(src_plug).connectTo(dst_plug, force=False)
        connected += 1

    cmds.inViewMessage(
        amg=f"Inputs duplicated: connected <hl>{connected}</hl> / "
            f"skipped <hl>{skipped}</hl> / failed <hl>{failed}</hl>",
        pos="topCenter",
        fade=True
    )

# 実行
duplicate_all_inputs_from_first_to_second()
