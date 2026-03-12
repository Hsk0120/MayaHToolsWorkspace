import maya.cmds as cmds

def duplicate_all_inputs_from_first_to_second(source=None, target=None):
    """
    選択ノード [source, target]
    source に入っている全入力コネクション(srcPlug -> source.attr) を
    target の同名 attr にも接続する。
    source 側の接続は保持、target 側は force しない。
    """

    sel = cmds.ls(sl=True, long=True) or []
    if source is None or target is None:
        if len(sel) < 2:
            raise RuntimeError("ノードを2つ選択してください（1つ目=元、2つ目=先）。")
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
        cmds.warning("元ノードに入力コネクションが見つかりません。")
        return

    connected = 0
    skipped = 0
    failed = 0

    for i in range(0, len(pairs), 2):
        print(sel[1])
        print(pairs[i].split("."))
        dst_plug = sel[1] + "." + pairs[i].split(".")[1]      # upstream plug
        src_plug = pairs[i + 1]  # source.attr

        print("src_plug:", src_plug)
        print("dst_plug:", dst_plug)


        cmds.connectAttr(src_plug, dst_plug, force=False)
        connected += 1

    cmds.inViewMessage(
        amg=f"入力複製 完了 : 接続 <hl>{connected}</hl> / "
            f"スキップ <hl>{skipped}</hl> / 失敗 <hl>{failed}</hl>",
        pos="topCenter",
        fade=True
    )

# 実行
duplicate_all_inputs_from_first_to_second()
