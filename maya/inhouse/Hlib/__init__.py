"""Hlib の公開 API と Maya ノードラッパーを提供するパッケージ。"""

import importlib
import sys

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
from .node import (
	Camera,
	Joint,
	Joints,
	Mesh,
	Node,
	Shape,
	SkinCluster,
	SkinClusters,
	Transform,
)


NODE_REGISTRY = NodeRegistry(Node)
NODE_REGISTRY.register("transform", Transform)
NODE_REGISTRY.register("joint", Joint)
NODE_REGISTRY.register("mesh", Mesh)
NODE_REGISTRY.register("camera", Camera)
NODE_REGISTRY.register("skinCluster", SkinCluster)


def reload_all():
	"""読み込み済みの Hlib モジュールを依存順に再読み込みする。

	旧フォルダ構成のモジュールキャッシュを削除してから、依存先を先に
	再読み込みする。Maya の Script Editor で Hlib を開発中に更新を反映する
	用途を想定している。

	Returns:
		tuple[module]: 再読み込みしたモジュール。Hlib パッケージ本体は最後に含まれる。
	"""
	package_name = __name__
	legacy_modules = (
		package_name + ".camera",
		package_name + ".datatypes",
		package_name + ".euler_rotation",
		package_name + ".joint",
		package_name + ".matrix",
		package_name + ".mesh",
		package_name + ".plug",
		package_name + ".quaternion",
		package_name + ".registry",
		package_name + ".rotation",
		package_name + ".scale",
		package_name + ".shape",
		package_name + ".shear",
		package_name + ".skincluster",
		package_name + ".transform",
		package_name + ".translation",
		package_name + ".vector",
	)
	for module_name in legacy_modules:
		sys.modules.pop(module_name, None)

	module_names = [
		name
		for name in sys.modules
		if name == package_name or name.startswith(package_name + ".")
	]

	# 依存先を先に再読み込みし、公開 API を持つパッケージ本体は最後に更新する。
	priority = {
		package_name + ".decorator": 1,
		package_name + ".math.vector": 2,
		package_name + ".math.quaternion": 3,
		package_name + ".math.rotation": 3,
		package_name + ".math.scale": 3,
		package_name + ".math.shear": 3,
		package_name + ".math.translation": 3,
		package_name + ".math.euler_rotation": 4,
		package_name + ".math.matrix": 5,
		package_name + ".math": 6,
		package_name + ".core.registry": 3,
		package_name + ".core.plug": 4,
		package_name + ".core": 5,
		package_name + ".node.node": 6,
		package_name + ".node.transform": 7,
		package_name + ".node.joint": 8,
		package_name + ".node.shape": 8,
		package_name + ".node.camera": 9,
		package_name + ".node.mesh": 9,
		package_name + ".node.skincluster": 9,
		package_name + ".node": 10,
		package_name + ".utils.progress": 11,
		package_name + ".utils": 12,
		package_name: 99,
	}
	module_names.sort(
		key=lambda name: (priority.get(name, 10), name.count("."), name)
	)
	reloaded = []
	for module_name in module_names:
		module = sys.modules.get(module_name)
		if module is None:
			continue
		reloaded.append(importlib.reload(module))

	return tuple(reloaded)


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


__all__ = [
	"Camera",
	"EulerRotation",
	"Joint",
	"Joints",
	"Matrix",
	"Mesh",
	"Node",
	"NodeRegistry",
	"NODE_REGISTRY",
	"Plug",
	"Rotation",
	"Quaternion",
	"Scale",
	"Shear",
	"Shape",
	"SkinCluster",
	"SkinClusters",
	"Transform",
	"Translation",
	"Vector",
	"ls",
	"node",
	"reload_all",
]

