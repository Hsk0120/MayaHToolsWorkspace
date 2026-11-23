"""選択2ノード間で入力接続を複製するユーティリティ。"""

import mlib
from mlib.decorator import undoChunk


def _get_input_source(plug, skip_conversion=False):
    """Plug の入力元を返す。

    元の ``cmds.connectionInfo`` と同じく、子のアトリビュートは親への入力も入力として扱う
    (親の入力元を返す)。

    Args:
        plug (mlib.Plug): 入力元を調べる Plug。
        skip_conversion (bool): unitConversion を飛ばした先の入力元を返すか。

    Returns:
        mlib.Plug | None: 入力元。入力が無ければ None。
    """
    while plug is not None:
        if plug.isDestination():
            return plug.getSource(skipConversionNodes=skip_conversion)
        plug = plug.getParent() if plug.isChild() else None
    return None


def _connect_attr(source_plug, target_plug, force=False, target_label=None):
    """接続先のロックを解除せずにアトリビュートを接続する。

    同じ接続が既にある場合と、接続先がロックされている場合は、元と同じ文言の
    RuntimeError にして呼び出し側へ伝える。

    Args:
        source_plug (mlib.Plug): 接続元のプラグ。
        target_plug (mlib.Plug): 接続先のプラグ。
        force (bool): 接続先の既存入力を置き換えるか。
        target_label (str | None): メッセージに出す接続先の名前。None なら Plug の名前。

    Raises:
        RuntimeError: 接続先がロックされている、または同じ接続が既にある場合。
    """
    target_label = target_label or target_plug.getFullName()
    if target_plug.isLocked():
        raise RuntimeError('Attribute is locked: {}'.format(target_label))
    if target_plug.isConnectedTo(source_plug, destination=False):
        raise RuntimeError(
            'Already connected: {} -> {}'.format(source_plug.getFullName(), target_label)
        )
    target_plug.connect(source_plug, force=force, unlock=False)


def copy_incoming_connections_from_first_to_second(force=False, skip_conversion=False):
    """1つ目ノードの入力接続を2つ目ノードへ複製します。

    Args:
        force (bool): 既存接続があっても強制接続するか。
        skip_conversion (bool): unitConversion をスキップして元接続元を使うか。

    Returns:
        dict[str, object]: コピー結果サマリ。
    """
    sel = mlib.ls(sl=True)
    if len(sel) < 2:
        raise RuntimeError('Select two nodes: first = source, second = destination.')

    src = sel[0]
    dst = sel[1]
    src_node = src.getFullName()
    dst_node = dst.getFullName()

    copied = []
    skipped = []
    errors = []

    # 複数の接続をまとめて1回の Undo で戻せるようにする。
    # すべてのアトリビュートを取得(getPlugs と違い、番号の決まらないマルチアトリビュートの子も listAttr と同じく含める)
    attrs = src.getAttrNames()

    with undoChunk('copyIncomingConnections'):
        for attr in attrs:
            src_plug = '{}.{}'.format(src_node, attr)
            dst_plug = '{}.{}'.format(dst_node, attr)

            # 複製先に同名アトリビュートが無ければスキップ
            if not mlib.objExists(dst_plug):
                skipped.append((src_plug, 'target attribute not found'))
                continue

            try:
                # 入力接続されている属性だけを対象にする(番号の決まらない子は接続を持てないので飛ばす)。
                if not src.hasAttr(attr):
                    continue
                # 接続元プラグを取得(unitConversion を飛ばす場合は、実質的な接続元)。
                input_src = _get_input_source(src.getPlug(attr), skip_conversion=skip_conversion)
                if input_src is None:
                    continue

                target = dst.getPlug(attr)
                # 既に同接続がある場合は重複接続を避ける。
                if target.isConnectedTo(input_src, destination=False):
                    continue

                _connect_attr(input_src, target, force=force, target_label=dst_plug)
                copied.append((input_src.getFullName(), dst_plug))

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