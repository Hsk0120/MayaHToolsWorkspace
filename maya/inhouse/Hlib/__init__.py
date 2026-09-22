"""Hlib の公開 API と Maya ノードラッパーを提供するパッケージ。"""

import importlib

# reload()で再実行された場合も、前回のcmds公開名を残さない。
_previous_command_exports = globals().get("_command_exports", ())
for _command_name in _previous_command_exports:
	globals().pop(_command_name, None)

from .core import initialize_node_api, initialize_plug_api, reload_package
from .scene import Namespace, Scene
from .components import Vertex, Vertices, CV, CVs, Edge, Edges, Face, Faces, UV, UVs

# Node/Joints/SkinClusters/Plug/ArrayPlug/CompoundPlug などは
# initialize_node_api/initialize_plug_api が globals() へ直接書き込むため、
# ここで .nodes/.plugs を明示 import する必要はない（二重初期化を避ける）。

_exports = sorted(set(initialize_node_api(__name__, globals())) | set(initialize_plug_api(__name__, globals())))

cmds = importlib.import_module(f"{__name__}.cmds")
_command_exports = tuple(cmds.__all__)
for _command_name in _command_exports:
	globals()[_command_name] = getattr(cmds, _command_name)

__all__ = ["cmds", "reload", *_command_exports, "Namespace", "Scene", "Vertex", "Vertices", "CV", "CVs", "Edge", "Edges", "Face", "Faces", "UV", "UVs", *_exports]


def reload():
	"""Hlib 配下の Python module を検出し、依存順に再読み込みする。

	現在存在する module を package から走査するため、新しい wrapper の追加や
	既存 module の削除も Maya の Script Editor から反映できる。依存関係は各
	module の globals にある Hlib class / function / module 参照から推定する。

	Returns:
		tuple[module]: 再読み込みした module の tuple。
	"""
	return reload_package(__name__)


