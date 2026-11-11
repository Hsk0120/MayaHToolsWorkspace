"""計算ノード(Condition・MultiplyDivide・AimMatrix 等)の共通の操作をまとめる(内部用)。

入力の設定(値の書込みと接続元の接続)、演算・モードの名前と番号の変換、マルチアトリビュートの
入力の追加・削除を、各クラスの公開メソッドから呼ぶ。Mayaのノードの継承は変えない。
"""

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from ..decorator import _edit_context


def chunk_name(node, method):
    """書込みメソッドのUndoチャンク名(``mlib<Class><Method>``)を返す。

    Args:
        node (Node): 対象の計算ノード。
        method (str): 公開メソッド名。

    Returns:
        str: Undoチャンク名。
    """
    return f"mlib{type(node).__name__}{method[:1].upper()}{method[1:]}"


def _source(value, geometry):
    """入力の値が接続元を指すなら、その Plug を返す。

    Args:
        value (object): 入力の値。
        geometry (str | None): ジオメトリの入力ならシェイプのMaya型名(``"nurbsCurve"`` 等)。

    Returns:
        Plug | None: 接続元。値として書き込む場合はNone。

    Raises:
        TypeError: ジオメトリの入力に、対応するシェイプ・Plug 以外を渡した場合。
        ValueError: ジオメトリの入力のTransformに、対応するシェイプが1つだけでない場合。
    """
    # plugs・nodes は計算ノードのクラスを読み込むため、循環importを避けて関数内で読み込む。
    from ..plugs.plug import Plug
    from .node import Node

    if isinstance(value, (Plug, om2.MPlug)) or isinstance(value, str):
        return Plug._resolve_input(value)
    if geometry is None:
        return None
    node = Node._resolve_input(value)
    if not node.isType(geometry) and node.hasFn(om2.MFn.kTransform):
        shapes = [shape for shape in node.getShapes() if shape.isType(geometry)]
        if len(shapes) != 1:
            raise ValueError(f"Expected exactly one {geometry} shape under {node}, got {len(shapes)}")
        node = shapes[0]
    if not node.isType(geometry):
        raise TypeError(f"Expected a {geometry} shape, got {node.getType()}: {node}")
    return node.getPlug("worldSpace")[node.mpath().instanceNumber()]


def set_inputs(node, method, values, geometry=None):
    """入力をまとめて設定し、ノードを返す。

    値は書き込み、Plug・MPlug・``"node.attr"`` の文字列は接続元として接続する(既存の入力は置き換える)。
    接続されている入力へ値を書く場合は、先に接続を外す。Noneの入力は変更しない。
    全ての接続元を解決してから書き込み、1回のUndoにまとめる。途中でMayaが拒否した場合は
    それまでの変更を戻す。

    Args:
        node (Node): 対象の計算ノード。
        method (str): 公開メソッド名(例外・Undoチャンク名に使う)。
        values (dict[str, object]): アトリビュート名から入力の値。
        geometry (dict[str, str] | None): ジオメトリの入力のアトリビュート名からシェイプのMaya型名。
            シェイプ(またはそれを1つだけ持つTransform)を渡すと、そのworldSpaceを接続する。

    Returns:
        Node: node自身。

    Raises:
        TypeError: 接続元の型が不正な場合。
        ValueError: ジオメトリの入力のTransformに、対応するシェイプが1つだけでない場合。
        RuntimeError: ノードが無効な場合、またはMayaが書込み・接続を拒否した場合。
    """
    node._require_valid(method)
    geometry = geometry or {}
    plans = [(node.getPlug(name), _source(value, geometry.get(name)), value)
             for name, value in values.items() if value is not None]
    with _edit_context(chunk_name(node, method), False, transaction=True):
        for target, source, value in plans:
            if source is not None:
                source.connectTo(target, force=True)
                continue
            if target.getSource() is not None:
                target.disconnect()
            target.set(value)
    return node


def enum_index(value, names, label):
    """名前または番号を、Mayaの列挙の番号へ変換する。

    Args:
        value (str | int): ``names`` の名前、または番号。
        names (tuple[str, ...]): 番号順の名前。
        label (str): 例外メッセージに使う引数名。

    Returns:
        int: 列挙の番号。

    Raises:
        TypeError: 文字列・int以外(boolを含む)の場合。
        ValueError: 未対応の名前・範囲外の番号の場合。選択肢を示す。
    """
    if isinstance(value, str):
        if value in names:
            return names.index(value)
    elif isinstance(value, int) and not isinstance(value, bool):
        if 0 <= value < len(names):
            return value
    else:
        raise TypeError(f"{label} must be a name or an index, got {type(value).__name__}")
    raise ValueError(f"Unsupported {label} {value!r} (choices: {', '.join(names)})")


def set_enum(node, method, attribute, value, names, label):
    """列挙のアトリビュートを名前または番号で設定し、ノードを返す。

    Args:
        node (Node): 対象の計算ノード。
        method (str): 公開メソッド名。
        attribute (str): 列挙のアトリビュート名。
        value (str | int): 名前または番号。
        names (tuple[str, ...]): 番号順の名前。
        label (str): 例外メッセージに使う引数名。

    Returns:
        Node: node自身。

    Raises:
        TypeError: :func:`enum_index` と同じ。
        ValueError: :func:`enum_index` と同じ。
        RuntimeError: ノードが無効な場合、またはMayaが書込みを拒否した場合。
    """
    index = enum_index(value, names, label)
    node._require_valid(method)
    with _edit_context(chunk_name(node, method), False):
        node.getPlug(attribute).set(index)
    return node


def get_enum(node, attribute, names):
    """列挙のアトリビュートの現在の名前を返す。

    Args:
        node (Node): 対象の計算ノード。
        attribute (str): 列挙のアトリビュート名。
        names (tuple[str, ...]): 番号順の名前。

    Returns:
        str: 現在の名前。
    """
    return names[node.getPlug(attribute).get()]


def choice(value, choices, label):
    """出力の種類などの選択肢を検証して返す。

    Args:
        value (str): 選んだ名前。
        choices (Iterable[str]): 選択肢。
        label (str): 例外メッセージに使う引数名。

    Returns:
        str: value。

    Raises:
        ValueError: 選択肢に無い場合。
    """
    choices = tuple(choices)
    if value not in choices:
        raise ValueError(f"Unsupported {label} {value!r} (choices: {', '.join(choices)})")
    return value


def element_indices(node, attribute):
    """マルチアトリビュートの既存要素の論理番号を昇順で返す。

    Args:
        node (Node): 対象の計算ノード。
        attribute (str): マルチアトリビュート名。

    Returns:
        list[int]: 論理番号。
    """
    return node.getPlug(attribute).getIndices()


def add_element(node, method, attribute, values, geometry=None):
    """マルチアトリビュートの末尾(既存の最大の番号+1)へ要素を足し、その番号を返す。

    Args:
        node (Node): 対象の計算ノード。
        method (str): 公開メソッド名。
        attribute (str): 番号を決めるマルチアトリビュート名。
        values (dict[str, object]): ``{index}`` を論理番号に置き換えるアトリビュートのパスから入力の値
            (例: ``{"input[{index}]": 1.0, "weight[{index}]": 0.5}``)。
        geometry (dict[str, str] | None): :func:`set_inputs` と同じ。

    Returns:
        int: 足した要素の論理番号。

    Raises:
        TypeError: :func:`set_inputs` と同じ。
        RuntimeError: :func:`set_inputs` と同じ。
    """
    indices = element_indices(node, attribute)
    index = indices[-1] + 1 if indices else 0
    set_inputs(node, method, {path.format(index=index): value for path, value in values.items()}, geometry)
    return index


def remove_elements(node, method, attributes, index):
    """マルチアトリビュートの同じ論理番号の要素を、接続ごと削除する。

    Args:
        node (Node): 対象の計算ノード。
        method (str): 公開メソッド名。
        attributes (Iterable[str]): マルチアトリビュート名。先頭で番号の存在を確かめる。
        index (int): 論理番号。

    Returns:
        Node: node自身。

    Raises:
        TypeError: indexがint以外(boolを含む)の場合。
        ValueError: 先頭のマルチアトリビュートに index の要素が無い場合。
        RuntimeError: ノードが無効な場合、またはMayaが削除を拒否した場合。
    """
    if not isinstance(index, int) or isinstance(index, bool):
        raise TypeError(f"index must be an int, got {type(index).__name__}")
    attributes = tuple(attributes)
    node._require_valid(method)
    if index not in element_indices(node, attributes[0]):
        raise ValueError(f"{node}.{attributes[0]} has no element {index}")
    with _edit_context(chunk_name(node, method), False):
        for attribute in attributes:
            if index in element_indices(node, attribute):
                cmds.removeMultiInstance(f"{node.getName()}.{attribute}[{index}]", b=True)
    return node
