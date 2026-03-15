import maya.cmds as cmds

def copy_incoming_connections_from_first_to_second(force=False, skip_conversion=False):
    sel = cmds.ls(sl=True, long=True) or []
    if len(sel) < 2:
        raise RuntimeError('ノードを2つ選択してください。1つ目=元、2つ目=複製先')

    src_node = sel[0]
    dst_node = sel[1]

    copied = []
    skipped = []
    errors = []

    # すべてのアトリビュートを取得
    attrs = cmds.listAttr(src_node) or []

    for attr in attrs:
        src_plug = '{}.{}'.format(src_node, attr)
        dst_plug = '{}.{}'.format(dst_node, attr)

        # 複製先に同名アトリビュートが無ければスキップ
        if not cmds.objExists(dst_plug):
            skipped.append((src_plug, 'target attribute not found'))
            continue

        try:
            # 入力接続されているアトリビュートか確認
            if not cmds.connectionInfo(src_plug, isDestination=True):
                continue

            # 接続元プラグを取得
            input_src = cmds.connectionInfo(src_plug, sourceFromDestination=True)
            if not input_src:
                continue

            # unitConversion を飛ばしたい場合
            if skip_conversion:
                cons = cmds.listConnections(
                    src_plug,
                    s=True, d=False,
                    p=True, c=False,
                    scn=True
                ) or []
                if cons:
                    input_src = cons[0]

            # すでに同じ接続があるなら何もしない
            if cmds.isConnected(input_src, dst_plug):
                continue

            cmds.connectAttr(input_src, dst_plug, force=force)
            copied.append((input_src, dst_plug))

        except Exception as e:
            errors.append((src_plug, str(e)))

    print('=== copied ===')
    for s, d in copied:
        print('{} -> {}'.format(s, d))

    print('=== skipped ===')
    for p, reason in skipped:
        print('{} : {}'.format(p, reason))

    print('=== errors ===')
    for p, reason in errors:
        print('{} : {}'.format(p, reason))

    return {
        'source_node': src_node,
        'target_node': dst_node,
        'copied': copied,
        'skipped': skipped,
        'errors': errors,
    }

if __name__ == '__main__':
    copy_incoming_connections_from_first_to_second(force=False, skip_conversion=False)