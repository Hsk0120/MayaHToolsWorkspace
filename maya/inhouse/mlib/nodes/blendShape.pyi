# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Maya の blendShape デフォーマを扱う。"""

import math
import re
import maya.api.OpenMaya as om2
import maya.api.OpenMayaAnim as oma2
import maya.cmds as cmds
import maya.mel as mel
from ..components.vertex import Vertex, Vertices
from ..core.attributeType import typed_data
from ..core.fastWrite import require_writable, set_attr
from ..decorator import _edit_context, _require_bool, undoChunk
from ..maths.vector import Vector
from ..plugs.plug import Plug
from ..util import _mirror_axis
from .geometryFilter import GeometryFilter
from .node import Node
from typing import Any, Iterable, Sequence
from mlib.json.nameMapping import NameMapping
from mlib.json.snapshot import ValidationReport
import os
import pathlib

_WEIGHT_ALIAS: Any
_ITEM_OFFSET: int
_FULL_ITEM: int
_MAX_INDEX: int
_TARGETS_FORMAT: str
_TARGETS_VERSION: int
_TARGETS_MODES: tuple


class BlendShape(GeometryFilter):
    """blendShapeデフォーマの参照と、ターゲットの照会・編集・JSON保存を提供する。

    ターゲット名はウェイト(``weight[i]``)のエイリアスで、Shape Editorやチャンネルボックスに
    表示される名前と同じ。``"smile_L" in blendShape`` はターゲット名の有無を返す。
    ターゲットを受け取るメソッドは、ターゲット名(str)・論理番号(int。boolは不可)・自身の
    ``weight`` の要素のPlugのいずれでも指定できる。複数のベース(変形対象)を持つ場合、ベースごとの
    操作は ``base`` で対象の形状(またはそのtransform)を選び、省略時は論理番号が最小のベースを使う。

    デルタはベースのオブジェクト空間の変位(cm)で、頂点番号と組にして扱う。in-betweenは
    ``fullWeight`` (1.0以外の項目のウェイト)で選ぶ。通常の更新はMaya標準コマンドで1回のUndoにまとめる。
    ``fast=True`` はデルタ・頂点マスクの書込みだけが持ち、OpenMayaで書き込んでUndoに記録しない。

    Note:
        ターゲットの除去は :meth:`removeTarget` を使う。``getPlug("weight").removeElement(i)`` は
        ウェイトの要素だけを消し、エイリアスと ``inputTarget[].inputTargetGroup[i]`` を残す。
    """
    def __contains__(self, name: str) -> bool:
        """ターゲット名(ウェイトのエイリアス)が存在するかを返す。

        Args:
            name (str): ターゲット名。

        Returns:
            bool: ターゲットが存在すればTrue。

        Raises:
            TypeError: nameが文字列以外の場合。
            RuntimeError: ノードが無効な場合。
        """
        ...
    def getTargetNames(self) -> list[str]:
        """ターゲット名を論理番号の順に取得する。

        Returns:
            list[str]: ウェイトのエイリアス。エイリアスの無いウェイト要素は含めない。

        Raises:
            RuntimeError: ノードが無効な場合。
        """
        ...
    def getTargetIndex(self, target: str | int | Plug) -> int:
        """ターゲットのウェイトの論理番号を取得する。

        Args:
            target (str | int | Plug): ターゲット名・論理番号・自身の ``weight`` の要素のPlug。

        Returns:
            int: ``weight`` の論理番号(``inputTargetGroup`` の番号と同じ)。

        Raises:
            TypeError: targetが対応しない型(boolを含む)の場合。
            ValueError: ターゲットが存在しない、または他のノード・別のアトリビュートのPlugの場合。
            RuntimeError: ノードが無効な場合。
        """
        ...
    def getWeightPlug(self, target: str | int | Plug) -> Plug:
        """ターゲットのウェイトのPlug(``weight[i]``)を取得する。

        Args:
            target (str | int | Plug): ターゲット名・論理番号・自身の ``weight`` の要素のPlug。

        Returns:
            Plug: ``weight`` の要素のPlug。接続・値の設定に使う。

        Raises:
            TypeError: targetが対応しない型(boolを含む)の場合。
            ValueError: ターゲットが存在しない、または他のノード・別のアトリビュートのPlugの場合。
            RuntimeError: ノードが無効な場合。
        """
        ...
    def getBaseGeometry(self) -> list[Node]:
        """変形する形状(出力ジオメトリ)を取得する。

        Returns:
            list[Node]: 変形対象の形状。geometryFilterの出力順。

        Raises:
            RuntimeError: ノードが無効な場合。
        """
        ...
    def addTarget(self, mesh: str | Node, name: str | None = ...) -> Plug:
        """ターゲットを空いている次の論理番号へ追加する(``cmds.blendShape(edit=True, target=...)`` 相当)。

        最初の変形対象(:meth:`getBaseGeometry` の先頭)に対するターゲットとして追加し、ウェイトは0。
        ターゲット形状との接続はMayaの既定どおり残す。Undo有効時は1回で戻せる。

        Args:
            mesh (str | Node): ターゲットの形状またはtransform。
            name (str | None): ターゲット名。Noneはメッシュの名前(Mayaの既定)。

        Returns:
            Plug: 追加したターゲットのウェイト(``weight[i]``)。

        Raises:
            TypeError: nameが文字列・None以外、またはmeshが対応しない型の場合。
            ValueError: nameが空文字列、同名のターゲットが既にある、またはmeshが無効な場合。
            RuntimeError: ノードが無効、変形対象が無い、またはMayaが追加を拒否した場合。
        """
        ...
    def removeTarget(self, target: str | int | Plug) -> BlendShape:
        """ターゲットを完全に取り除く。ターゲット形状が削除済みでもよい。

        ``cmds.blendShape(edit=True, remove=True, target=...)`` と同じく、ウェイトの要素・エイリアス・
        全変形対象の ``inputTarget[].inputTargetGroup[i]``・Shape Editorの所属情報を取り除く
        (Maya標準の ``blendShapeDeleteTargetGroup`` を使う)。ウェイトへの入力接続は切断し、
        ウェイトを駆動するcombinationShapeノードはMayaの規則どおり削除する。ターゲット形状のノードは
        削除しない。Undo有効時は1回で戻せる。

        Args:
            target (str | int | Plug): ターゲット名・論理番号・自身の ``weight`` の要素のPlug。

        Returns:
            BlendShape: 自身。

        Raises:
            TypeError: targetが対応しない型(boolを含む)の場合。
            ValueError: ターゲットが存在しない場合。
            RuntimeError: ノードが無効、ウェイトがロックされている、またはMayaが除去を拒否した場合。
        """
        ...
    def getInBetweenWeights(self, target: str | int | Plug, base: str | Node | None = ...) -> list[float]:
        """ターゲットのin-betweenの項目のウェイトを昇順で取得する。

        ``inputTargetItem`` の論理番号を `` (番号 - 5000) / 1000`` で換算し、1.0(ターゲット本体)を除く。
        現在の ``weight`` の値は参照しない。

        Args:
            target (str | int | Plug): ターゲット名・論理番号・自身の ``weight`` の要素のPlug。
            base (str | Node | None): ベースの形状またはそのtransform。Noneは論理番号が最小のベース。

        Returns:
            list[float]: in-betweenの項目のウェイト。in-betweenが無ければ空。

        Raises:
            TypeError: target・baseが対応しない型の場合。
            ValueError: ターゲットが存在しない、baseがこのblendShapeのベースでない、
                またはターゲットがそのベースにデータを持たない場合。
        """
        ...
    def addInBetween(self, target: str | int | Plug, geometry: str | Node, weight: float, base: str | Node | None = ..., relative: bool = ...) -> BlendShape:
        """既存のターゲットへin-betweenを追加する(``cmds.blendShape(edit=True, inBetween=True)`` 相当)。

        ``geometry`` との接続はMayaの既定どおり残す。Undo有効時は1回で戻せる。

        Args:
            target (str | int | Plug): 親のターゲット名・論理番号・自身の ``weight`` の要素のPlug。
            geometry (str | Node): in-betweenの形状。ベースと頂点数が同じメッシュ(またはそのtransform)。
            weight (float): in-betweenが完全に効くウェイト。0・1以外で、-5以上、0.001刻み。
            base (str | Node | None): ベースの形状またはそのtransform。Noneは論理番号が最小のベース。
            relative (bool): Trueはターゲット本体からの相対、Falseは絶対(Mayaの既定)のin-between。

        Returns:
            BlendShape: 自身。

        Raises:
            TypeError: target・geometry・base・weightの型が不正、relativeがbool以外、
                またはgeometryがメッシュでない場合。
            ValueError: ターゲットが存在しない、weightが0・1・既存の項目・範囲外・0.001刻みでない、
                または頂点数がベースと違う場合。
        """
        ...
    def removeInBetween(self, target: str | int | Plug, weight: float) -> BlendShape:
        """指定ウェイトのin-betweenを全ベースから取り除く(Maya標準の ``blendShapeDeleteInBetweenTarget``)。

        Undo有効時は1回で戻せる。

        Args:
            target (str | int | Plug): 親のターゲット名・論理番号・自身の ``weight`` の要素のPlug。
            weight (float): 取り除くin-betweenのウェイト。1.0(ターゲット本体)は不可。

        Returns:
            BlendShape: 自身。

        Raises:
            TypeError: targetの型が不正、またはweightが数値でない場合。
            ValueError: ターゲットが存在しない、またはそのウェイトのin-betweenが無い場合。
        """
        ...
    def getTargetWeights(self, target: str | int | Plug, base: str | Node | None = ...) -> list[float]:
        """ターゲットの頂点マスク(``inputTargetGroup[i].targetWeights``)を頂点番号順に取得する。

        値が書かれていない頂点は、Mayaの既定どおり1.0として返す。

        Args:
            target (str | int | Plug): ターゲット名・論理番号・自身の ``weight`` の要素のPlug。
            base (str | Node | None): ベースの形状またはそのtransform。Noneは論理番号が最小のベース。

        Returns:
            list[float]: ベースの頂点数と同じ長さの新しいlist。

        Raises:
            TypeError: target・baseが対応しない型、またはベースがメッシュでない場合。
            ValueError: ターゲットが存在しない、baseがこのblendShapeのベースでない、
                またはターゲットがそのベースにデータを持たない場合。
        """
        ...
    def setTargetWeights(self, target: str | int | Plug, weights: Sequence[float] | dict[int, float], base: str | Node | None = ..., *, fast: bool = ...) -> BlendShape:
        """ターゲットの頂点マスク(``inputTargetGroup[i].targetWeights``)を設定する。

        全頂点の並びは頂点番号順に全頂点を、辞書は指定した頂点だけを書き換える。値は0〜1へ制限しない。
        通常は番号が1ずつ増える頂点を範囲指定の1回の ``setAttr`` にまとめ、全体を1回のUndoにする。

        Args:
            target (str | int | Plug): ターゲット名・論理番号・自身の ``weight`` の要素のPlug。
            weights (Sequence[float] | dict[int, float]): 頂点数分の値、または頂点番号と値の辞書。
            base (str | Node | None): ベースの形状またはそのtransform。Noneは論理番号が最小のベース。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            BlendShape: 自身。

        Raises:
            TypeError: target・base・値の型が不正、fastがbool以外、またはベースがメッシュでない場合。
            ValueError: ターゲットが存在しない、並びの長さが頂点数と違う、値が有限でない場合。
            IndexError: 頂点番号が範囲外の場合。
            RuntimeError: アトリビュートがロック・入力接続されている、またはMayaが書込みを拒否した場合。
        """
        ...
    def getTargetDeltas(self, target: str | int | Plug, base: str | Node | None = ..., fullWeight: float = ...) -> dict[int, Vector]:
        """ターゲット(またはin-between)の項目に保存されたデルタを取得する。

        ターゲット形状が接続中なら、Mayaが評価した現在のデルタを返す。値はベースのオブジェクト空間の
        変位(cm)で、変位を持つ頂点だけを含む。

        Args:
            target (str | int | Plug): ターゲット名・論理番号・自身の ``weight`` の要素のPlug。
            base (str | Node | None): ベースの形状またはそのtransform。Noneは論理番号が最小のベース。
            fullWeight (float): 項目のウェイト。1.0はターゲット本体、それ以外はin-between。

        Returns:
            dict[int, Vector]: 頂点番号と変位。

        Raises:
            TypeError: target・baseの型が不正、またはfullWeightが数値でない場合。
            ValueError: ターゲットまたはそのウェイトの項目が存在しない場合。
        """
        ...
    def setTargetDeltas(self, target: str | int | Plug, deltas: dict[int, Sequence[float]], base: str | Node | None = ..., fullWeight: float = ..., disconnect: bool = ..., *, fast: bool = ...) -> BlendShape:
        """ターゲット(またはin-between)の項目のデルタ全体を置き換える。指定しない頂点は変位0になる。

        ターゲット形状が接続中の場合、既定では変更せずに拒否する(接続から再計算されて上書きされるため)。
        ``disconnect=True`` は接続を切ってから書き込む。他の項目のデルタは変えない。

        Args:
            target (str | int | Plug): ターゲット名・論理番号・自身の ``weight`` の要素のPlug。
            deltas (dict[int, Sequence[float]]): 頂点番号と変位(xyz、cm)。
            base (str | Node | None): ベースの形状またはそのtransform。Noneは論理番号が最小のベース。
            fullWeight (float): 項目のウェイト。1.0はターゲット本体、それ以外はin-between。
            disconnect (bool): Trueはターゲット形状の接続を切ってから書き込む。既定False。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            BlendShape: 自身。

        Raises:
            TypeError: 引数の型が不正、disconnect・fastがbool以外、またはベースがメッシュでない場合。
            ValueError: ターゲット・項目が存在しない、または変位が3個の有限な数値でない場合。
            IndexError: 頂点番号が範囲外の場合。
            RuntimeError: ターゲット形状が接続中でdisconnect=False、またはMayaが書込みを拒否した場合。
        """
        ...
    def getTargetVertices(self, target: str | int | Plug, base: str | Node | None = ..., fullWeight: float = ..., *, tolerance: float = ...) -> Vertices:
        """デルタの長さがしきい値を超える頂点を取得する。

        現在の ``weight``・envelope・頂点マスクは判定に使わない。

        Args:
            target (str | int | Plug): ターゲット名・論理番号・自身の ``weight`` の要素のPlug。
            base (str | Node | None): ベースの形状またはそのtransform。Noneは論理番号が最小のベース。
            fullWeight (float): 項目のウェイト。1.0はターゲット本体、それ以外はin-between。
            tolerance (float): これ以下の長さ(cm)の変位を除く。有限の0以上。既定0は変位0だけを除く。

        Returns:
            Vertices: ベースの頂点。番号の昇順。

        Raises:
            TypeError: 引数の型が不正、またはベースがメッシュでない場合。
            ValueError: ターゲット・項目が存在しない、またはtoleranceが負・有限でない場合。
        """
        ...
    def resetTargetVertices(self, target: str | int | Plug, vertices: int | Vertex | Vertices | Iterable[int | Vertex], base: str | Node | None = ..., fullWeight: float = ..., disconnect: bool = ..., *, fast: bool = ...) -> BlendShape:
        """指定した頂点の変位を0に戻す。残りの頂点の変位はそのまま残す。

        ターゲット形状が接続中の場合の扱いは :meth:`setTargetDeltas` と同じ。変位を持たない頂点だけを
        指定した場合は何も変えない。

        Args:
            target (str | int | Plug): ターゲット名・論理番号・自身の ``weight`` の要素のPlug。
            vertices (int | Vertex | Vertices | Iterable[int | Vertex]): ベースの頂点または頂点番号。
            base (str | Node | None): ベースの形状またはそのtransform。Noneは論理番号が最小のベース。
            fullWeight (float): 項目のウェイト。1.0はターゲット本体、それ以外はin-between。
            disconnect (bool): Trueはターゲット形状の接続を切ってから書き込む。既定False。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            BlendShape: 自身。

        Raises:
            TypeError: 引数の型が不正、またはベースがメッシュでない場合。
            ValueError: ターゲット・項目が存在しない、または頂点が別の形状のものの場合。
            IndexError: 頂点番号が範囲外の場合。
            RuntimeError: ターゲット形状が接続中でdisconnect=False、またはMayaが書込みを拒否した場合。
        """
        ...
    def reduceTargetDeltas(self, target: str | int | Plug, tolerance: float = ..., base: str | Node | None = ..., fullWeight: float = ..., disconnect: bool = ..., *, fast: bool = ...) -> BlendShape:
        """デルタの長さがしきい値以下の頂点を、項目のデータから取り除く。

        結果の変形は変わらず(しきい値以下の変位は0になる)、保存するデータが減る。
        ターゲット形状が接続中の場合の扱いは :meth:`setTargetDeltas` と同じ。

        Args:
            target (str | int | Plug): ターゲット名・論理番号・自身の ``weight`` の要素のPlug。
            tolerance (float): これ以下の長さ(cm)の変位を取り除く。有限の0以上。既定0は変位0だけ。
            base (str | Node | None): ベースの形状またはそのtransform。Noneは論理番号が最小のベース。
            fullWeight (float): 項目のウェイト。1.0はターゲット本体、それ以外はin-between。
            disconnect (bool): Trueはターゲット形状の接続を切ってから書き込む。既定False。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            BlendShape: 自身。

        Raises:
            TypeError: 引数の型が不正、またはベースがメッシュでない場合。
            ValueError: ターゲット・項目が存在しない、またはtoleranceが負・有限でない場合。
            RuntimeError: ターゲット形状が接続中でdisconnect=False、またはMayaが書込みを拒否した場合。
        """
        ...
    def mirrorTarget(self, target: str | int | Plug, axis: str | int = ..., positiveToNegative: bool = ..., base: str | Node | None = ...) -> BlendShape:
        """ターゲットの片側の変形を反対側へミラーする(``cmds.blendShape(edit=True, mirrorTarget=...)``)。

        オブジェクト空間の座標で対称の頂点を探す。Undo有効時は1回で戻せる。

        Args:
            target (str | int | Plug): ターゲット名・論理番号・自身の ``weight`` の要素のPlug。
            axis (str | int): 反転する軸。``"x"``・``"y"``・``"z"`` (大文字小文字は問わない)、
                ミラー面の ``"YZ"`` 等、または0〜2。
            positiveToNegative (bool): Trueは正の側を負の側へ、Falseは負の側を正の側へ写す。
            base (str | Node | None): ベースの形状またはそのtransform。Noneは論理番号が最小のベース。

        Returns:
            BlendShape: 自身。

        Raises:
            TypeError: 引数の型が不正、またはベースがメッシュでない場合。
            ValueError: ターゲットが存在しない、またはaxisが軸でない場合。
            RuntimeError: ターゲット形状が接続中の場合(先に :meth:`duplicateTarget` 等でベイクする)。
        """
        ...
    def flipTarget(self, target: str | int | Plug, axis: str | int = ..., base: str | Node | None = ...) -> BlendShape:
        """ターゲットの変形を左右反転する(``cmds.blendShape(edit=True, flipTarget=...)``)。

        左右別のターゲットを作る場合は、:meth:`duplicateTarget` で複製してから反転する。
        Undo有効時は1回で戻せる。

        Args:
            target (str | int | Plug): ターゲット名・論理番号・自身の ``weight`` の要素のPlug。
            axis (str | int): 反転する軸。``"x"``・``"y"``・``"z"``、ミラー面の ``"YZ"`` 等、または0〜2。
            base (str | Node | None): ベースの形状またはそのtransform。Noneは論理番号が最小のベース。

        Returns:
            BlendShape: 自身。

        Raises:
            TypeError: 引数の型が不正、またはベースがメッシュでない場合。
            ValueError: ターゲットが存在しない、またはaxisが軸でない場合。
            RuntimeError: ターゲット形状が接続中の場合。
        """
        ...
    def duplicateTarget(self, target: str | int | Plug, name: str | None = ...) -> Plug:
        """ターゲットを、全ベースのデルタ・in-between・頂点マスクごと新しい論理番号へ複製する。

        接続中のターゲット形状は現在の形をベイクし、複製は接続を持たない。新しいウェイトは0で、
        外部のドライバーは複製しない。Shape Editorでは元のターゲットと同じフォルダの末尾に置く。
        Undo有効時は1回で戻せる。

        Args:
            target (str | int | Plug): 複製元のターゲット名・論理番号・自身の ``weight`` の要素のPlug。
            name (str | None): 新しいターゲット名。Noneは ``<元の名前>Copy`` (重なれば末尾に番号)。

        Returns:
            Plug: 新しいターゲットのウェイト(``weight[i]``)。

        Raises:
            TypeError: targetの型が不正、nameが文字列・None以外、またはベースがメッシュでない場合。
            ValueError: ターゲットが存在しない、またはnameが空・既存のアトリビュートと重なる場合。
        """
        ...
    def replaceTarget(self, target: str | int | Plug, geometry: str | Node, base: str | Node | None = ..., fullWeight: float = ...) -> BlendShape:
        """ターゲット(またはin-between)の項目の形状を、別のメッシュへの接続に差し替える。

        ターゲット名・ウェイトの値と接続・頂点マスクは保つ。以後のデルタは接続したメッシュから
        計算される。Undo有効時は1回で戻せる。

        Args:
            target (str | int | Plug): ターゲット名・論理番号・自身の ``weight`` の要素のPlug。
            geometry (str | Node): 新しいターゲット形状。ベースと頂点数が同じメッシュ(またはそのtransform)。
            base (str | Node | None): ベースの形状またはそのtransform。Noneは論理番号が最小のベース。
            fullWeight (float): 項目のウェイト。1.0はターゲット本体、それ以外はin-between。

        Returns:
            BlendShape: 自身。

        Raises:
            TypeError: 引数の型が不正、またはgeometry・ベースがメッシュでない場合。
            ValueError: ターゲット・項目が存在しない、または頂点数がベースと違う場合。
            RuntimeError: Mayaが接続を拒否した場合。
        """
        ...
    def targetEdit(self, target: str | int | Plug | None = ..., state: bool = ..., fullWeight: float = ...) -> BlendShape:
        """ターゲットの編集モード(Shape EditorのEdit)を開始・終了する(``cmds.sculptTarget``)。

        開始中はベースのスカルプトがターゲットのデルタへ書き込まれる。Undo有効時は1回で戻せる。

        Args:
            target (str | int | Plug | None): 開始するターゲット。開始時は必須で、終了時は使わない。
            state (bool): Trueは開始、FalseはこのblendShapeの編集モードを終了する。
            fullWeight (float): 編集する項目のウェイト。1.0はターゲット本体、それ以外はin-between。

        Returns:
            BlendShape: 自身。

        Raises:
            TypeError: targetの型が不正、stateがbool以外、またはfullWeightが数値でない場合。
            ValueError: 開始時にtargetが無い、またはターゲット・項目が存在しない場合。
        """
        ...
    def getTargetsData(self) -> dict:
        """全ターゲットを、JSONへ書ける辞書として取得する(:meth:`setTargetsData` で戻せる)。

        ベースごとの頂点数と頂点マスク(baseWeights)、ターゲットごとの名前・論理番号・現在のウェイト・
        ウェイトの入力接続(ドライバー)・頂点マスク・デルタ・in-between、Shape Editorのフォルダを含む。
        接続中のターゲット形状は現在の形をベイクしたデルタとして記録する。

        Returns:
            dict: ``bases``・``targets``・``folders`` を持つ新しい辞書。数学型を含まない。

        Raises:
            TypeError: ベースがメッシュでない場合。
            RuntimeError: ノードが無効な場合。
        """
        ...
    def setTargetsData(self, data: dict, *, nameMap: dict[str, str] | None = ..., replace: Iterable[tuple[str, str]] | None = ..., namespaceMap: dict[str, str] | None = ..., mode: str = ...) -> ValidationReport:
        """:meth:`getTargetsData` の辞書からターゲットを復元する。

        ベースは論理番号で対応させ、頂点数が違えば何も変えずにValueErrorにする。``mode="replace"`` (既定)は
        同じ名前のターゲットの中身を置き換え、無いターゲットを追加する。``mode="empty"`` はターゲットの
        無いblendShapeにだけ読み込む。ウェイトのドライバーは ``nameMap``・``replace``・``namespaceMap``
        (:class:`mlib.json.NameMapping` の規則)で対応付けて再接続し、見つからないものは値だけを設定して
        警告する。全体を1回のUndoにまとめ、途中で失敗した場合は巻き戻す。

        Args:
            data (dict): :meth:`getTargetsData` の形の辞書。
            nameMap (dict[str, str] | None): 名前空間を除いた名前の対応表。
            replace (Iterable[tuple[str, str]] | None): 順に当てる文字列置換。
            namespaceMap (dict[str, str] | None): 名前空間の対応。
            mode (str): ``"replace"`` または ``"empty"``。

        Returns:
            ValidationReport: 見つからなかったドライバー(``missing``)と、書けずに飛ばしたもの(``skipped``)。

        Raises:
            TypeError: dataが辞書でない、またはmodeが文字列でない場合。
            ValueError: データの形が違う、modeが不正、``mode="empty"`` でターゲットがある、
                ベースが無い・頂点数が違う、またはターゲット名が既存のアトリビュートと重なる場合。
            RuntimeError: Undoが無効、またはMayaが書込みを拒否した場合。
        """
        ...
    def exportTargets(self, path: str | os.PathLike) -> pathlib.Path:
        """全ターゲットをJSONファイルへ書き出す(:meth:`getTargetsData` の内容。形式 ``mlib.blendShapeTargets``)。

        Args:
            path (str | os.PathLike): 書き出し先。

        Returns:
            pathlib.Path: 書き出したファイルの絶対パス。

        Raises:
            TypeError: ベースがメッシュでない場合。
            OSError: 書き出しに失敗した場合。
        """
        ...
    def importTargets(self, path: str | os.PathLike, *, nameMap: dict[str, str] | None = ..., replace: Iterable[tuple[str, str]] | None = ..., namespaceMap: dict[str, str] | None = ..., mode: str = ...) -> ValidationReport:
        """:meth:`exportTargets` で書き出したファイルからターゲットを復元する(:meth:`setTargetsData`)。

        Args:
            path (str | os.PathLike): 読み込むファイル。
            nameMap (dict[str, str] | None): 名前空間を除いた名前の対応表。
            replace (Iterable[tuple[str, str]] | None): 順に当てる文字列置換。
            namespaceMap (dict[str, str] | None): 名前空間の対応。
            mode (str): ``"replace"`` または ``"empty"``。

        Returns:
            ValidationReport: :meth:`setTargetsData` の結果。

        Raises:
            ValueError: 形式名・版が違う、または :meth:`setTargetsData` が拒否した場合。
            OSError: 読み込みに失敗した場合。
        """
        ...
    def _target_items(self) -> list[tuple[int, str]]:
        """エイリアスのあるウェイト要素を ``(論理番号, 名前)`` の並びで返す。

        Returns:
            list[tuple[int, str]]: OpenMayaのエイリアス一覧から得た対応。

        Raises:
            RuntimeError: ノードが無効な場合。
        """
        ...
    def _target_lookup(self, name: str) -> int | None:
        """ターゲット名の論理番号を返す。無ければNone。

        Args:
            name (str): ターゲット名。

        Returns:
            int | None: 論理番号。

        Raises:
            TypeError: nameが文字列以外の場合。
            RuntimeError: ノードが無効な場合。
        """
        ...
    def _alias_of(self, index: int) -> str | None:
        """論理番号のウェイトのエイリアスを返す。無ければNone。

        Args:
            index (int): ウェイトの論理番号。

        Returns:
            str | None: エイリアス。
        """
        ...
    def _target_indices(self) -> list[int]:
        """ターゲットの論理番号を昇順で返す。

        エイリアスのあるウェイト要素と、いずれかのベースに項目(``inputTargetItem``)を持つ番号の和集合。

        Returns:
            list[int]: 論理番号。
        """
        ...
    def _target_index(self, target: str | int | Plug) -> int:
        """ターゲットの指定を論理番号にする。

        Args:
            target (str | int | Plug): ターゲット名・論理番号・自身の ``weight`` の要素のPlug。

        Returns:
            int: 存在するターゲットの論理番号。

        Raises:
            TypeError: 対応しない型(boolを含む)の場合。
            ValueError: ターゲットが存在しない、または他のノード・別のアトリビュートのPlugの場合。
        """
        ...
    def _base_indices(self) -> list[int]:
        """ベース(出力ジオメトリ)の論理番号を昇順で返す。

        Returns:
            list[int]: 論理番号。
        """
        ...
    def _base_index(self, base: str | Node | None) -> int:
        """ベースの指定を論理番号にする。

        Args:
            base (str | Node | None): ベースの形状またはそのtransform。Noneは論理番号が最小のベース。

        Returns:
            int: ベースの論理番号。

        Raises:
            TypeError: 対応しない型の場合。
            ValueError: ベースが無い、またはこのblendShapeのベースでない場合。
        """
        ...
    def _base_shape(self, bi: int) -> Node:
        """ベースの論理番号のメッシュを返す。

        Args:
            bi (int): ベースの論理番号。

        Returns:
            Node: ベースのメッシュ(Mesh)。

        Raises:
            TypeError: ベースがメッシュでない場合。
        """
        ...
    def _vertex_count(self, bi: int) -> int:
        """ベースの頂点数を返す。

        Args:
            bi (int): ベースの論理番号。

        Returns:
            int: 頂点数。

        Raises:
            TypeError: ベースがメッシュでない場合。
        """
        ...
    def _require_vertex_count(self, bi: int, shape: Node):
        """形状の頂点数がベースと同じことを確かめる。

        Args:
            bi (int): ベースの論理番号。
            shape (Node): 比べるメッシュ。

        Raises:
            ValueError: 頂点数が違う場合。
        """
        ...
    def _resolve_group(self, target: str | int | Plug, base: str | Node | None) -> tuple[int, int]:
        """ターゲットとベースを解決し、そのベースにターゲットの項目があることを確かめる。

        Args:
            target (str | int | Plug): ターゲットの指定。
            base (str | Node | None): ベースの指定。

        Returns:
            tuple[int, int]: ベースとターゲットの論理番号。

        Raises:
            ValueError: ターゲットがそのベースに項目を持たない場合。
        """
        ...
    def _resolve_item(self, target: str | int | Plug, base: str | Node | None, weight: float) -> tuple[int, int, int]:
        """ターゲット・ベース・項目のウェイトを解決し、項目が存在することを確かめる。

        Args:
            target (str | int | Plug): ターゲットの指定。
            base (str | Node | None): ベースの指定。
            weight (float): 項目のウェイト。

        Returns:
            tuple[int, int, int]: ベース・ターゲット・項目の論理番号。

        Raises:
            ValueError: その項目が無い場合。
        """
        ...
    def _unused_index(self, reserved: Iterable[int] = ...) -> int:
        """ウェイト・ターゲット・エイリアスのどれにも使われていない最小の論理番号を返す。

        Args:
            reserved (Iterable[int]): 追加で使用中とみなす番号。

        Returns:
            int: 空いている論理番号。
        """
        ...
    def _require_new_name(self, name: str):
        """新しいターゲット名が使えることを確かめる。

        Args:
            name (str): ターゲット名。

        Raises:
            TypeError: 文字列でない場合。
            ValueError: 空、または既存のアトリビュート・エイリアスと重なる場合。
        """
        ...
    def _copy_name(self, source: str) -> str:
        """複製の既定の名前(``<元の名前>Copy``、重なれば末尾に番号)を返す。

        Args:
            source (str): 元のターゲット名。

        Returns:
            str: 使われていない名前。
        """
        ...
    def _mirror_axis_name(self, bi: int, index: int, axis: str | int) -> str:
        """ミラー・反転の条件を確かめ、Mayaのsymmetryの軸名を返す。

        Args:
            bi (int): ベースの論理番号。
            index (int): ターゲットの論理番号。
            axis (str | int): 軸の指定。

        Returns:
            str: ``"x"``・``"y"``・``"z"``。

        Raises:
            TypeError: ベースがメッシュでない、またはaxisの型が不正な場合。
            ValueError: axisが軸でない場合。
            RuntimeError: ターゲット形状が接続中の場合。
        """
        ...
    def _attr(self, path: str) -> str:
        """アトリビュートのパスに、ノードの一意な名前を付ける。

        Args:
            path (str): ノード名を含まないアトリビュートのパス。

        Returns:
            str: ``<ノード>.<パス>``。
        """
        ...
    def _mplug(self, path: str) -> om2.MPlug:
        """アトリビュートのパスのMPlugを返す。

        Args:
            path (str): ノード名を含まないアトリビュートのパス。

        Returns:
            om2.MPlug: Plug。
        """
        ...
    def _existing(self, path: str) -> list[int]:
        """マルチアトリビュートの既存の論理番号を、要素を作らずに昇順で返す。

        Args:
            path (str): マルチアトリビュートのパス。

        Returns:
            list[int]: 論理番号。
        """
        ...
    @staticmethod
    def _group_path(bi: int, index: int) -> str:
        """ターゲットのグループのパスを返す。

        Args:
            bi (int): ベースの論理番号。
            index (int): ターゲットの論理番号。

        Returns:
            str: ``inputTarget[bi].inputTargetGroup[index]``。
        """
        ...
    @classmethod
    def _item_path(cls, bi: int, index: int, item: int) -> str:
        """ターゲットの項目のパスを返す。

        Args:
            bi (int): ベースの論理番号。
            index (int): ターゲットの論理番号。
            item (int): 項目の論理番号。

        Returns:
            str: ``inputTarget[bi].inputTargetGroup[index].inputTargetItem[item]``。
        """
        ...
    def _item_indices(self, bi: int, index: int) -> list[int]:
        """ターゲットのそのベースの項目の論理番号を昇順で返す。

        Args:
            bi (int): ベースの論理番号。
            index (int): ターゲットの論理番号。

        Returns:
            list[int]: 項目の論理番号。グループが無ければ空。
        """
        ...
    def _read_deltas(self, path: str) -> tuple[list[int], list[tuple[float, float, float]]]:
        """項目のデルタを読む。接続中ならMayaが評価した値。

        Args:
            path (str): 項目のパス。

        Returns:
            tuple[list[int], list[tuple[float, float, float]]]: 頂点番号と変位。

        Raises:
            RuntimeError: Mayaが返した頂点と変位の数が合わない場合。
        """
        ...
    def _write_deltas(self, path: str, indices: list[int], offsets: list[Sequence[float]], *, fast: bool = ...):
        """項目のデルタを書き、相対in-betweenの補助の値を消す(Mayaが再計算する)。

        通常は ``setAttr`` の2回(pointArray・componentList。連続する頂点は範囲にまとめる)で書く。

        Args:
            path (str): 項目のパス。
            indices (list[int]): 頂点番号(重複なし)。
            offsets (list[Sequence[float]]): 頂点番号と同じ数の変位。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        """
        ...
    def _release_input(self, path: str, disconnect: bool, *, fast: bool = ...):
        """項目のターゲット形状の接続を、disconnect=Trueなら切り、Falseなら拒否する。

        Args:
            path (str): 項目のパス。
            disconnect (bool): 接続を切るか。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Raises:
            RuntimeError: 接続中でdisconnect=Falseの場合。
        """
        ...
    def _remove_vertices(self, path: str, remove: set[int], disconnect: bool, *, fast: bool = ...):
        """項目のデータから指定した頂点を取り除く。該当が無ければ何も変えない。

        Args:
            path (str): 項目のパス。
            remove (set[int]): 取り除く頂点番号。
            disconnect (bool): 接続中のターゲット形状を切るか。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        """
        ...
    def _vertex_indices(self, vertices: int | Vertex | Vertices | Iterable[int | Vertex], bi: int) -> list[int]:
        """頂点の指定を、ベースの範囲内の頂点番号にする。

        Args:
            vertices (int | Vertex | Vertices | Iterable[int | Vertex]): 頂点の指定。
            bi (int): ベースの論理番号。

        Returns:
            list[int]: 頂点番号。

        Raises:
            TypeError: 対応しない型の場合。
            ValueError: 別の形状の頂点の場合。
            IndexError: 範囲外の番号の場合。
        """
        ...
    def _read_vertex_weights(self, path: str, count: int) -> list[float]:
        """頂点ごとの値のマルチアトリビュートを、未設定を1.0として読む。

        Args:
            path (str): マルチアトリビュートのパス。
            count (int): 頂点数。

        Returns:
            list[float]: 頂点番号順の値。
        """
        ...
    def _write_vertex_weights(self, path: str, values: dict[int, float], *, fast: bool = ...):
        """頂点ごとの値を書く。通常は連続する番号を範囲指定の1回のsetAttrにまとめる。

        Args:
            path (str): マルチアトリビュートのパス。
            values (dict[int, float]): 検証済みの頂点番号と値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        """
        ...
    def _capture_target(self, index: int, driver: bool = ...) -> dict:
        """ターゲットの全ベースのデータを、JSONへ書ける辞書として取得する。

        Args:
            index (int): ターゲットの論理番号。
            driver (bool): Trueならウェイトの入力接続を記録する。

        Returns:
            dict: ``name``・``index``・``weight``・``driver``・``inBetweens``・``bases`` を持つ辞書。
        """
        ...
    def _capture_inbetweens(self, index: int) -> list[dict]:
        """ターゲットのin-betweenの情報(``inbetweenInfoGroup``)を取得する。

        Args:
            index (int): ターゲットの論理番号。

        Returns:
            list[dict]: ``weight``・``relative``・``name``・``interpolation``・``visibility``・``curve`` の辞書。
        """
        ...
    def _create_target(self, index: int, bases: Iterable[int]):
        """空のターゲットを論理番号へ作る(Shape Editorの空のターゲットの追加と同じ手順)。

        ベースを一時的に複製してターゲットとして追加し、複製を削除してからデルタを0にする。
        ウェイト・エイリアス・Shape Editorの所属はMayaの既定のまま。

        Args:
            index (int): 使われていない論理番号。
            bases (Iterable[int]): ターゲットを作るベースの論理番号。
        """
        ...
    def _write_target(self, index: int, record: dict, name: str | None, created: bool = ...):
        """取得したターゲットのデータ(:meth:`_capture_target` の形)をターゲットへ書く。

        デルタ・in-between・頂点マスク・エイリアスを書き、記録に無い項目は取り除く。
        ウェイトの値と接続は扱わない。Undoのまとまりは呼出し側が持つ。

        Args:
            index (int): 書込み先の論理番号。
            record (dict): ターゲットのデータ。
            name (str | None): ターゲット名。Noneはエイリアスを付けない。
            created (bool): Trueなら書く前に空のターゲットを作る。
        """
        ...
    def _write_inbetweens(self, index: int, inbetweens: list[dict]):
        """in-betweenの情報を書き、記録に無いものを取り除く。

        Args:
            index (int): ターゲットの論理番号。
            inbetweens (list[dict]): :meth:`_capture_inbetweens` の形の情報。
        """
        ...
    def _plan_targets(self, data: dict, mapping: NameMapping, report: ValidationReport) -> list[tuple[dict, int, bool, Plug | None]]:
        """復元するデータを検査し、書込み先の論理番号とドライバーを決める。シーンは変えない。

        Args:
            data (dict): :meth:`getTargetsData` の形の辞書。
            mapping (NameMapping): ドライバーの名前の対応付け。
            report (ValidationReport): 問題の記録先。

        Returns:
            list[tuple[dict, int, bool, Plug | None]]: ターゲットのデータ・書込み先の番号・
                新しく作るか・ドライバーのPlug。
        """
        ...
    def _apply_targets(self, data: dict, plan: list, report: ValidationReport):
        """検査済みの計画どおりにターゲットを書く。Undoのまとまりは呼出し側が持つ。

        Args:
            data (dict): :meth:`getTargetsData` の形の辞書。
            plan (list): :meth:`_plan_targets` の結果。
            report (ValidationReport): 飛ばしたものの記録先。
        """
        ...


class _Directories:
    """Shape Editorのフォルダ(``targetDirectory``・``parentDirectory``)を読み書きする内部の補助。

    ``targetDirectory[d]`` はフォルダ(0は最上位)で、``childIndices`` に子の並びを持つ(0以上はターゲットの
    論理番号、負の値は ``-<フォルダの番号>``)。``parentDirectory[i]`` はターゲットの所属フォルダ。
    読んだ内容を変更してから :meth:`write` で変わったものだけをcmdsで書く。
    """
    def __init__(self, folders: dict[int, dict], parents: dict[int, int]) -> None:
        """読んだ内容を保持する。

        Args:
            folders (dict[int, dict]): フォルダの番号と ``name``・``parent``・``children``・``weight``・``visibility``。
            parents (dict[int, int]): ターゲットの論理番号と所属フォルダ。
        """
        ...
    @classmethod
    def read(cls, node: BlendShape) -> _Directories:
        """blendShapeのフォルダを読む。

        Args:
            node (BlendShape): 対象のblendShape。

        Returns:
            _Directories: 読んだ内容。
        """
        ...
    def parentOf(self, index: int) -> int:
        """ターゲットの所属フォルダを返す。

        Args:
            index (int): ターゲットの論理番号。

        Returns:
            int: フォルダの番号。不明なら0(最上位)。
        """
        ...
    def move(self, index: int, folder: int, after: int | None = ...):
        """ターゲットをフォルダへ移す。

        Args:
            index (int): ターゲットの論理番号。
            folder (int): 移動先のフォルダの番号。
            after (int | None): このターゲットの直後に置く。Noneは末尾。
        """
        ...
    def toData(self, targets: Iterable[int]) -> list[dict]:
        """最上位からのフォルダの木を、JSONへ書けるlistにする。

        Args:
            targets (Iterable[int]): 書き出すターゲットの論理番号。

        Returns:
            list[dict]: 最上位の子の並び。``{"target": 番号}`` または
                ``{"folder": 名前, "weight": ..., "visibility": ..., "children": [...]}``。
        """
        ...
    def restore(self, entries: list[dict], index_map: dict[int, int]):
        """保存したフォルダの木に合わせて、復元したターゲットを配置する。

        フォルダは親と名前で既存のものを使い、無ければ作る。各フォルダの子の並びは、保存した順を先頭に、
        保存に無い既存の子をその後に置く。

        Args:
            entries (list[dict]): :meth:`toData` の形の木。
            index_map (dict[int, int]): 保存時のターゲットの番号と、復元先の番号。
        """
        ...
    def write(self, node: BlendShape):
        """変わった値だけを ``cmds.setAttr`` で書く。

        Args:
            node (BlendShape): 対象のblendShape。
        """
        ...
    def _place(self, entries: list[dict], folder: int, index_map: dict[int, int]):
        """木の1階層をフォルダへ配置する。

        Args:
            entries (list[dict]): 子の並び。
            folder (int): 配置先のフォルダの番号。
            index_map (dict[int, int]): 保存時と復元先のターゲットの番号。
        """
        ...
    def _new_folder(self, parent: int, name: str) -> int:
        """空のフォルダを作る(Mayaの ``blendShapeUnusedTargetDirectoryIndex`` と同じ番号の選び方)。

        Args:
            parent (int): 親フォルダの番号。
            name (str): フォルダ名。

        Returns:
            int: 作ったフォルダの番号。
        """
        ...
    def _ensure_root(self):
        """最上位のフォルダ(0)が無ければ作る。"""
        ...

def _weight_item(weight: float) -> int:
    """項目のウェイトを ``inputTargetItem`` の論理番号(``5000 + weight * 1000``)にする。

    Args:
        weight (float): 項目のウェイト。-5以上、0.001刻み。

    Returns:
        int: 論理番号。

    Raises:
        TypeError: 数値でない(boolを含む)場合。
        ValueError: 有限でない、範囲外、または0.001刻みで表せない場合。
    """
    ...

def _mesh_shape(value: str | Node) -> Node:
    """形状またはtransformを、中間オブジェクトでない1つのメッシュにする。

    Args:
        value (str | Node): メッシュまたはそのtransform。

    Returns:
        Node: メッシュ。

    Raises:
        TypeError: メッシュでない場合。
        ValueError: transformに中間オブジェクトでないメッシュが1つでない場合。
    """
    ...

def _runs(indices: Sequence[int]) -> list[tuple[int, int]]:
    """昇順の番号を、1ずつ増える区間の ``(最初, 最後)`` に分ける。

    Args:
        indices (Sequence[int]): 昇順の番号。

    Returns:
        list[tuple[int, int]]: 区間。
    """
    ...

def _vertex_values(weights: Sequence[float] | dict[int, float], count: int) -> dict[int, float]:
    """頂点ごとの値の指定を、検証済みの辞書にする。

    Args:
        weights (Sequence[float] | dict[int, float]): 全頂点の並び、または頂点番号と値。
        count (int): 頂点数。

    Returns:
        dict[int, float]: 頂点番号と値。

    Raises:
        TypeError: 型が不正な場合。
        ValueError: 並びの長さが違う、または値が有限でない場合。
        IndexError: 頂点番号が範囲外の場合。
    """
    ...

def _delta_values(deltas: dict[int, Sequence[float]], count: int) -> list[tuple[int, tuple[float, float, float]]]:
    """デルタの指定を、頂点番号の昇順の ``(番号, (x, y, z))`` にする。

    Args:
        deltas (dict[int, Sequence[float]]): 頂点番号と変位。
        count (int): 頂点数。

    Returns:
        list[tuple[int, tuple[float, float, float]]]: 検証済みの変位。

    Raises:
        TypeError: 辞書でない、番号がintでない、または変位が数値の並びでない場合。
        ValueError: 変位が3個の有限な数値でない場合。
        IndexError: 頂点番号が範囲外の場合。
    """
    ...

def _tolerance(value: float) -> float:
    """しきい値を検証する。

    Args:
        value (float): 0以上の有限な数値。

    Returns:
        float: しきい値。

    Raises:
        TypeError: 数値でない場合。
        ValueError: 負または有限でない場合。
    """
    ...

def _sparse(values: list[float]) -> dict:
    """頂点ごとの値から、既定値1.0でないものだけを取り出す。

    Args:
        values (list[float]): 頂点番号順の値。

    Returns:
        dict: ``{"indices": [...], "values": [...]}``。
    """
    ...

def _dense(sparse: dict, count: int) -> list[float]:
    """:func:`_sparse` の形を、全頂点の値の並びに戻す。

    Args:
        sparse (dict): ``{"indices": [...], "values": [...]}``。
        count (int): 頂点数。

    Returns:
        list[float]: 頂点番号順の値。
    """
    ...

def _data_index(value: object, label: str) -> int:
    """データの論理番号を検証する。

    Args:
        value (object): 値。
        label (str): メッセージに使う名前。

    Returns:
        int: 論理番号。

    Raises:
        ValueError: 0以上の論理番号でない場合。
    """
    ...

def _check_sparse(value: object, count: int):
    """:func:`_sparse` の形と頂点番号の範囲を検証する。

    Args:
        value (object): 検証する値。
        count (int): 頂点数。

    Raises:
        ValueError: 形・番号・値が不正な場合。
    """
    ...

def _check_target(target: object, counts: dict[int, int], report: ValidationReport) -> dict | None:
    """1つのターゲットのデータを検証する。

    ベースが見つからない・頂点数が違うものはreportへ記録する(ベースの検査で記録済み)。

    Args:
        target (object): ターゲットのデータ。
        counts (dict[int, int]): 検査に通ったベースの論理番号と頂点数。
        report (ValidationReport): 問題の記録先。

    Returns:
        dict | None: 検証済みのデータ。ベースの問題で使えなければNone。

    Raises:
        ValueError: データの形が違う場合。
    """
    ...
