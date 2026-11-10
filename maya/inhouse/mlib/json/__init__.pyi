# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""シーンのデータをJSONへ保存・復元する部品と、複数ノードのスナップショットを提供する。

下の層は数学型の変換(:mod:`.codec`)・ヘッダー付きファイル(:mod:`.file`)・ノード/Plug/コンポーネントの
参照と名前の対応付け、中の層は :class:`Snapshot` 基底。1つのノードが持つデータ(スキンウェイト等)は
各ノードのクラスのメソッドから保存する。
"""

from . import codec, file
from .animationSnapshot import AnimationSnapshot
from .attributesSnapshot import AttributesSnapshot
from .codec import decode, encode
from .componentRef import ComponentRef
from .drivenKeysSnapshot import DrivenKeysSnapshot
from .file import Header, dump, load
from .nameMapping import NameMapping
from .nodeRef import NodeRef
from .plugRef import PlugRef
from .poseSnapshot import PoseSnapshot
from .selectionSnapshot import SelectionSnapshot
from .snapshot import Snapshot, ValidationReport

__all__ = ['AnimationSnapshot', 'AttributesSnapshot', 'ComponentRef', 'DrivenKeysSnapshot', 'Header', 'NameMapping', 'NodeRef', 'PlugRef', 'PoseSnapshot', 'SelectionSnapshot', 'Snapshot', 'ValidationReport', 'codec', 'decode', 'dump', 'encode', 'file', 'load']
