"""選択2ノード間で入力接続を複製する簡易ツール。"""

import maya.cmds as cmds

import mlib
from mlib.decorator import undoChunk


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
        sel = mlib.ls(sl=True)
        if len(sel) < 2:
            raise RuntimeError("Select two nodes (first = source, second = destination).")
        source, target = sel[0].getFullName(), sel[1].getFullName()
    # 表示する名前は、元と同じく渡された名前(選択なら完全な名前)をそのまま使う。
    target_name = target
    source = mlib.getNode(source)
    target = mlib.getNode(target)

    # source の「入力」コネクションを (source.attr, srcPlug) ペアで取得
    pairs = source.getConnections(source=True, destination=False, asPair=True)

    if not pairs:
        cmds.warning("No incoming connections found on the source node.")
        return

    connected = 0
    skipped = 0
    failed = 0

    with undoChunk("duplicateInputsFromFirstToSecond"):
        for source_side, src_plug in pairs:
            # source 側の入力先属性名を target 側の同名属性へマッピングする。
            attribute = source_side.getFullName().split(".", 1)[1]
            dst_name = target_name + "." + attribute  # target.attr

            try:
                if not target.hasAttr(attribute):
                    raise RuntimeError("No object matches name: " + dst_name)
                dst_plug = target.getPlug(attribute)
                if dst_plug.isConnectedTo(src_plug, destination=False):
                    skipped += 1
                    continue
                if dst_plug.isLocked():
                    raise RuntimeError("Attribute is locked: " + dst_name)
                # force しないため、別の入力が既にある場合は mlib がエラーにする。
                dst_plug.connect(src_plug)
                connected += 1
            except Exception as e:
                failed += 1
                cmds.warning("Connection failed: {} -> {} ({})".format(src_plug.getFullName(), dst_name, e))

    cmds.inViewMessage(
        amg=f"Inputs duplicated: connected <hl>{connected}</hl> / "
            f"skipped <hl>{skipped}</hl> / failed <hl>{failed}</hl>",
        pos="topCenter",
        fade=True
    )


if __name__ == "__main__":
    # 実行
    duplicate_all_inputs_from_first_to_second()
