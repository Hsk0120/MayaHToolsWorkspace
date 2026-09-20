"""Hlib の公開 API と Maya ノードラッパーを提供するパッケージ。"""

import importlib
import pkgutil
import sys
import types

import maya.cmds as cmds

_node_module_name = __name__ + ".node"
_loaded_node_module = sys.modules.get(_node_module_name)
if _loaded_node_module is not None and not hasattr(_loaded_node_module, "__path__"):
	sys.modules.pop(_node_module_name, None)
	globals().pop("node", None)

from .core import NodeRegistry, Plug
from .math import (
	EulerRotation,
	Matrix,
	Quaternion,
	Rotation,
	Scale,
	Shear,
	Translation,
	Vector,
)
def _initialize_node_api():
	"""node package を読み込み、公開 class と registry を構築する。"""
	global _node_package, _node_wrappers, _node_exports
	global Node, Shape, Transform, NODE_REGISTRY

	_node_package = importlib.import_module(__name__ + ".node")
	if not hasattr(_node_package, "_discovered_wrappers"):
		_node_package = importlib.reload(_node_package)

	_node_wrappers = _node_package._discovered_wrappers
	_node_exports = _node_package._discovered_exports
	for export_name in _node_exports:
		globals().pop(export_name, None)
	globals().update(_node_exports)

	Node = _node_package.Node
	Shape = _node_package.Shape
	Transform = _node_package.Transform
	NODE_REGISTRY = NodeRegistry(Node)
	for node_type, wrapper_class in _node_wrappers.items():
		NODE_REGISTRY.register(node_type, wrapper_class)


_initialize_node_api()


def reload_all():
	"""Hlib 配下の Python module を検出し、依存順に再読み込みする。

	現在存在する module を package から走査するため、新しい wrapper の追加や
	既存 module の削除も Maya の Script Editor から反映できる。依存関係は各
	module の globals にある Hlib class / function / module 参照から推定する。

	Returns:
		tuple[module]: 再読み込みした module の tuple。
	"""
	package_name = __name__
	module_names = _discover_module_names(package_name)
	loaded_names = {
		name
		for name in sys.modules
		if name == package_name or name.startswith(package_name + ".")
	}
	for stale_name in loaded_names - set(module_names):
		sys.modules.pop(stale_name, None)
	for module_name in module_names:
		importlib.import_module(module_name)
	module_names = _reload_order(module_names)
	reloaded = []
	for module_name in module_names:
		module = sys.modules.get(module_name)
		if module is None:
			continue
		reloaded.append(importlib.reload(module))

	return tuple(reloaded)


def _discover_module_names(package_name):
	"""パッケージ配下の現在存在する Python module 名を取得する。

	Args:
		package_name (str): module を走査する package の完全修飾名。

	Returns:
		tuple[str]: package 自身を含む検出済み module 名。
	"""
	package = sys.modules[package_name]
	names = {package_name}
	for module_info in pkgutil.walk_packages(package.__path__, package_name + "."):
		names.add(module_info.name)
	return tuple(sorted(names))


def _reload_order(module_names):
	"""module 内の参照から依存先を推定し、reload 順を作る。

	Args:
		module_names (iterable[str]): reload 対象の完全修飾 module 名。

	Returns:
		list[str]: 依存先が先になる reload 順の module 名。
	"""
	module_set = set(module_names)
	dependencies = {
		name: _module_dependencies(sys.modules[name], module_set)
		for name in module_names
	}
	order = []
	visited = set()
	visiting = set()

	def visit(name):
		if name in visited:
			return
		if name in visiting:
			return
		visiting.add(name)
		for dependency in sorted(dependencies[name]):
			visit(dependency)
		visiting.remove(name)
		visited.add(name)
		order.append(name)

	for name in sorted(module_names):
		visit(name)
	return order


def _module_dependencies(module, module_names):
	"""module の globals から Hlib 内の依存 module 名を抽出する。

	Args:
		module (types.ModuleType): 依存関係を調べる module。
		module_names (set[str]): reload 対象として許可する module 名。

	Returns:
		set[str]: module が参照している Hlib module 名。
	"""
	dependencies = set()
	for value in vars(module).values():
		if isinstance(value, types.ModuleType):
			owner = value.__name__
		else:
			owner = getattr(value, "__module__", None)
		if owner in module_names and owner != module.__name__:
			dependencies.add(owner)
	return dependencies


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
		return _node_package.Joints(names)
	if node_type == "skinCluster":
		return _node_package.SkinClusters(names)
	return [_wrap_node(name) for name in names]


def node(name):
	"""Maya ノード名から最も具体的な Hlib ラッパーを生成する。

	Args:
		name (str): Maya シーン上のノード名。

	Returns:
		Node: NodeRegistry が解決したラッパー。joint、mesh、camera などは
			対応する派生クラスになる。
	"""
	return NODE_REGISTRY.resolve(name)


def _wrap_node(name):
	"""解決済みの Maya ノード名を最適な Hlib クラスでラップする。

	Args:
		name (str): Maya シーン上のノード名。

	Returns:
		Node: NodeRegistry が解決したラッパー。
	"""
	return NODE_REGISTRY.wrap(name, cmds.nodeType(name))


__all__ = ["ls", "node", "reload_all", *sorted(_node_exports)]

