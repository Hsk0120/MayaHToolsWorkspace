# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Maya の blendShape デフォーマを扱う。"""

import re
import maya.api.OpenMaya as om2
import maya.api.OpenMayaAnim as oma2
import maya.cmds as cmds
import maya.mel as mel
from ..core.object import Object
from ..decorator import _require_bool, undoChunk
from .node import Node
from typing import Any, Iterable
from mlib.plugs.plug import Plug

_WEIGHT_ALIAS: Any


class BlendShape(Node):
    """blendShapeデフォーマの参照と、ターゲットの名前による照会・追加・除去を提供する。

    ターゲット名はウェイト(``weight[i]``)のエイリアスで、Shape Editorやチャンネルボックスに
    表示される名前と同じ。``"smile_L" in blendShape`` はターゲット名の有無を返す。
    作成・追加・除去はMaya標準コマンドを使い、fast引数は持たない(OpenMayaに同等の編集APIが無い)。

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
    @classmethod
    def create(cls, base: str | Node, targets: str | Node | Iterable[str | Node] = ..., name: str | None = ..., frontOfChain: bool = ...) -> BlendShape:
        """形状にblendShapeを作成し、ターゲットを登録する(``cmds.blendShape`` 相当)。

        ``cmds.blendShape`` 専用の特化ビルダー。ターゲットは指定順に論理番号0から登録し、
        ターゲット名はMayaの規則どおりターゲットのtransform名(名前空間を含む短い名前)になる。
        ターゲット形状との接続はMayaの既定どおり残す。Undo有効時は1回で戻せる。

        Args:
            base (str | Node): 変形するメッシュ等の形状またはtransform。
            targets (str | Node | Iterable[str | Node]): ターゲットの形状またはtransform。
                省略時はターゲットの無いblendShapeを作る(後から :meth:`addTarget` で追加する)。
            name (str | None): 作成名。NoneならMayaの自動命名。
            frontOfChain (bool): Trueは既存デフォーマ(skinCluster等)より前、つまり変形の最初に
                置く(リグで一般的な「ブレンドシェイプ → スキン」の順)。Falseは最後に置く。

        Returns:
            BlendShape: 作成したblendShape。

        Raises:
            TypeError: frontOfChainがbool以外、nameが文字列・None以外、または対象が対応しない型の場合。
            ValueError: nameが空文字列、または対象が空・無効な場合。
            RuntimeError: 名前を解決できない、またはMayaが作成を拒否した場合。
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
    def getTargetIndex(self, name: str) -> int:
        """ターゲット名に対応するウェイトの論理番号を取得する。

        Args:
            name (str): ターゲット名。

        Returns:
            int: ``weight`` の論理番号(``inputTargetGroup`` の番号と同じ)。

        Raises:
            TypeError: nameが文字列以外の場合。
            ValueError: ターゲットが存在しない場合。
            RuntimeError: ノードが無効な場合。
        """
        ...
    def getWeightPlug(self, name: str) -> Plug:
        """ターゲット名に対応するウェイトのPlug(``weight[i]``)を取得する。

        Args:
            name (str): ターゲット名。

        Returns:
            Plug: ``weight`` の要素のPlug。接続・値の設定に使う。

        Raises:
            TypeError: nameが文字列以外の場合。
            ValueError: ターゲットが存在しない場合。
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
    def removeTarget(self, name: str) -> BlendShape:
        """ターゲットを完全に取り除く。ターゲット形状が削除済みでもよい。

        ``cmds.blendShape(edit=True, remove=True, target=...)`` と同じく、ウェイトの要素・エイリアス・
        全変形対象の ``inputTarget[].inputTargetGroup[i]``・Shape Editorの所属情報を取り除く
        (Maya標準の ``blendShapeDeleteTargetGroup`` を使う)。ウェイトへの入力接続は切断し、
        ウェイトを駆動するcombinationShapeノードはMayaの規則どおり削除する。ターゲット形状のノードは
        削除しない。Undo有効時は1回で戻せる。

        Args:
            name (str): ターゲット名。

        Returns:
            BlendShape: 自身。

        Raises:
            TypeError: nameが文字列以外の場合。
            ValueError: ターゲットが存在しない場合。
            RuntimeError: ノードが無効、ウェイトがロックされている、またはMayaが除去を拒否した場合。
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
