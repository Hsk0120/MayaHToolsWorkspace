"""必要なノードの生成時だけ標準同梱プラグインをロードする。"""

from .plugin import Plugin

HIK_NODE_TYPES = frozenset((
    'HIKCharacterNode', 'HIKSolverNode', 'HIKRetargeterNode',
    'HIKControlSetNode', 'HIKSkeletonGeneratorNode',
))


def ensure_node_plugin(node_type):
    """対応する標準プラグインをロードする。他の型には何もしない。

    Args:
        node_type (str): 作成するMayaノード型。
    """
    if node_type in HIK_NODE_TYPES:
        Plugin('mayaHIK').ensure_loaded()
