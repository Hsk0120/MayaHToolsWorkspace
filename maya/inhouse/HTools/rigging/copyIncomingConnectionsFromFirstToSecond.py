"""選択2ノード間で入力接続を複製するユーティリティ。"""

import maya.cmds as cmds


def _connect_attr(source_plug, target_plug, force=False):
    """接続先のロックを解除せずにアトリビュートを接続する。

    cmds.connectAttr は同じ接続が既にあると warning だけで終わるため、
    ロック中・接続済みの場合は RuntimeError にして呼び出し側へ伝える。

    Args:
        source_plug (str): 接続元のプラグ名。
        target_plug (str): 接続先のプラグ名。
        force (bool): 接続先の既存入力を置き換えるか。

    Raises:
        RuntimeError: 接続先がロックされている、または同じ接続が既にある場合。
    """
    if cmds.getAttr(target_plug, lock=True):
        raise RuntimeError('Attribute is locked: {}'.format(target_plug))
    if cmds.isConnected(source_plug, target_plug):
        raise RuntimeError(
            'Already connected: {} -> {}'.format(source_plug, target_plug)
        )
    cmds.connectAttr(source_plug, target_plug, force=force)


def copy_incoming_connections_from_first_to_second(force=False, skip_conversion=False):
    """1つ目ノードの入力接続を2つ目ノードへ複製します。

    Args:
        force (bool): 既存接続があっても強制接続するか。
        skip_conversion (bool): unitConversion をスキップして元接続元を使うか。

    Returns:
        dict[str, object]: コピー結果サマリ。
    """
    sel = cmds.ls(sl=True, long=True) or []
    if len(sel) < 2:
        raise RuntimeError('Select two nodes: first = source, second = destination.')

    src_node = sel[0]
    dst_node = sel[1]

    copied = []
    skipped = []
    errors = []

    # すべてのアトリビュートを取得
    attrs = cmds.listAttr(src_node) or []

    # 複数の接続をまとめて1回の Undo で戻せるようにする。
    cmds.undoInfo(openChunk=True, chunkName='copyIncomingConnections')
    try:
        for attr in attrs:
            src_plug = '{}.{}'.format(src_node, attr)
            dst_plug = '{}.{}'.format(dst_node, attr)

            # 複製先に同名アトリビュートが無ければスキップ
            if not cmds.objExists(dst_plug):
                skipped.append((src_plug, 'target attribute not found'))
                continue

            try:
                # 入力接続されている属性だけを対象にする。
                if not cmds.connectionInfo(src_plug, isDestination=True):
                    continue

                # 接続元プラグを取得
                input_src = cmds.connectionInfo(src_plug, sourceFromDestination=True)
                if not input_src:
                    continue

                # unitConversion を飛ばす場合、実質的な接続元プラグを再取得する。
                if skip_conversion:
                    cons = cmds.listConnections(
                        src_plug,
                        s=True, d=False,
                        p=True, c=False,
                        scn=True
                    ) or []
                    if cons:
                        input_src = cons[0]

                # 既に同接続がある場合は重複接続を避ける。
                if cmds.isConnected(input_src, dst_plug):
                    continue

                _connect_attr(input_src, dst_plug, force=force)
                copied.append((input_src, dst_plug))

            except Exception as e:
                errors.append((src_plug, str(e)))
    finally:
        cmds.undoInfo(closeChunk=True)

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