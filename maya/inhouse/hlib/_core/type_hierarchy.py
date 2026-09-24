"""Maya ノードタイプの継承チェーンを取得・キャッシュする。"""

import maya.cmds as cmds

#: node_type -> 継承チェーン(自身を先頭、基底型へ向かう順)の tuple。
_INHERITED_TYPES_CACHE = {}


def inherited_node_types(node_type):
    """指定ノードタイプの継承チェーンを取得する。

    ``cmds.nodeType(node_type, isTypeName=True, inherited=True)`` は
    ノードの実体を必要とせず型名だけで継承関係を照会できる一方、都度
    Maya に問い合わせるとやや低速なため、型名ごとに結果をキャッシュする。
    Maya API 2.0 に同等の照会手段が無いため cmds を使用する。

    Args:
        node_type (str): Maya の nodeType 名。

    Returns:
        tuple[str, ...]: node_type 自身を先頭に、直接の親から基底型へ
            向かう順の継承チェーン。Maya が認識しない型名の場合は
            node_type 自身のみを含む1要素の tuple。
    """
    cached = _INHERITED_TYPES_CACHE.get(node_type)
    if cached is not None:
        return cached
    try:
        chain = cmds.nodeType(node_type, isTypeName=True, inherited=True) or [node_type]
    except RuntimeError:
        chain = [node_type]
    chain = tuple(reversed(chain))
    _INHERITED_TYPES_CACHE[node_type] = chain
    return chain


def clear_cache():
    """キャッシュを消去する。

    Returns:
        None: 値を返さない。
    """
    _INHERITED_TYPES_CACHE.clear()


__all__ = ["inherited_node_types", "clear_cache"]
