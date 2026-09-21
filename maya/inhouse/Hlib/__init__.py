"""Hlib の公開 API と Maya ノードラッパーを提供するパッケージ。"""

import maya.cmds as cmds
from .core import initialize_node_api, initialize_plug_api, reload_package
from .nodes import Node, Joints, SkinClusters
from .plugs import Plug, ArrayPlug, CompoundPlug

_exports = sorted(set(initialize_node_api(__name__, globals())) | set(initialize_plug_api(__name__, globals())))
__all__ = ["ls", "reload_all", *_exports]


def reload_all():
	"""Hlib 配下の Python module を検出し、依存順に再読み込みする。

	現在存在する module を package から走査するため、新しい wrapper の追加や
	既存 module の削除も Maya の Script Editor から反映できる。依存関係は各
	module の globals にある Hlib class / function / module 参照から推定する。

	Returns:
		tuple[module]: 再読み込みした module の tuple。
	"""
	return reload_package(__name__)


def ls(*args, **kwargs):
	"""Maya ノードを検索し、対応する Hlib ラッパーとして返す。

	``maya.cmds.ls`` の引数をそのまま受け取る。``type="joint"`` と
	``type="skinCluster"`` の場合は、それぞれ専用コレクションを返す。

	Args:
		*args: ``maya.cmds.ls`` へ渡す位置引数。
		**kwargs: ``maya.cmds.ls`` へ渡すキーワード引数。

	Returns:
		list[Node] | Joints | SkinClusters: 検索結果をラップした値。
	"""
	names = cmds.ls(*args, **kwargs) or []
	node_type = kwargs.get("type")
	if node_type == "joint":
		return Joints(names)
	if node_type == "skinCluster":
		return SkinClusters(names)
	return [Node(name) for name in names]


