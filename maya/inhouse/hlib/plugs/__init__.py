"""ラッパークラスを明示公開し、Mayaの型との対応を宣言する。"""

# reloadはモジュール辞書を保持するため、前回の公開名を取り除く。
for _name in globals().get("__all__", ()):
    globals().pop(_name, None)

# 旧初期化状態を、読み込み済みセッションに残さない。
for _name in ("_discovered_wrappers", "_discovered_exports",
              "discover_node_package", "discover_plug_package", "TYPE_CHECKING"):
    globals().pop(_name, None)

from .plug import Plug
from .arrayPlug import ArrayPlug
from .compoundPlug import CompoundPlug
from .boolPlug import BoolPlug
from .double3Plug import Double3Plug
from .doubleAnglePlug import DoubleAnglePlug
from .doubleLinearPlug import DoubleLinearPlug
from .doublePlug import DoublePlug
from .enumPlug import EnumPlug
from .floatPlug import FloatPlug
from .longPlug import LongPlug
from .matrixPlug import MatrixPlug
from .messagePlug import MessagePlug
from .shortPlug import ShortPlug
from .stringPlug import StringPlug
from .timePlug import TimePlug

# 公開名と型対応は別の責務として明示する。
__all__ = [
    "ArrayPlug",
    "BoolPlug",
    "CompoundPlug",
    "Double3Plug",
    "DoubleAnglePlug",
    "DoubleLinearPlug",
    "DoublePlug",
    "EnumPlug",
    "FloatPlug",
    "LongPlug",
    "MatrixPlug",
    "MessagePlug",
    "Plug",
    "ShortPlug",
    "StringPlug",
    "TimePlug",
]

_WRAPPER_CLASSES = {
    "bool": BoolPlug,
    "double": DoublePlug,
    "double3": Double3Plug,
    "doubleAngle": DoubleAnglePlug,
    "doubleLinear": DoubleLinearPlug,
    "enum": EnumPlug,
    "float": FloatPlug,
    "long": LongPlug,
    "matrix": MatrixPlug,
    "message": MessagePlug,
    "short": ShortPlug,
    "string": StringPlug,
    "time": TimePlug,
}
