# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""マルチアトリビュートの論理番号と要素プラグを扱う。"""

import operator
from contextlib import nullcontext
import maya.api.OpenMaya as om2
import maya.cmds as cmds
from ..core.attributeType import _convert_angles, _convert_units, _plain_angle_unit, is_internal_data_type
from ..core.attributeType import value_reader
from ..decorator import _require_bool, undoChunk
from .plug import MAX_LOGICAL_INDEX, Plug, _instance_count
from typing import Iterator
from mlib.nodes.node import Node



class MultiPlug(Plug):
    """マルチアトリビュート全体を参照し、疎な論理番号と要素Plugを扱う。

    doubleArray等の単一Plugの配列データとは異なる。``multi[index]`` は論理番号の
    参照、反復は既存要素、get()は値の取得。欠番は参照だけでは作られず、set/connectで実体化する。
    maya.cmdsへは ``str(multi)`` で渡す。要素がコンパウンドアトリビュートのPlugの場合も文字列化し、mlib.selectにはそのまま渡せる。
    """
    def __getitem__(self, index: int) -> Plug:
        """論理番号を指定し、既存または未作成のマルチアトリビュートの要素を参照する。

        リスト上の位置ではないため、既存番号が[2, 10]なら[10]で後者を参照する。
        取得だけでは値を読み出さず、欠番も実体化しない。要素へのset/connectが作成を担当する。

        Args:
            index (int): 0〜2147483647の論理番号。負数・sliceは使えない。

        Returns:
            Plug: 同じ所有Nodeを共有する新しい要素ラッパー。値やノードの複製ではない。
                worldSpace要素の番号を指定しても、所有Nodeの保持DAGパスは切り替えない。

        Raises:
            TypeError: indexがboolまたは整数以外の場合。
            IndexError: 論理番号が0〜2147483647の範囲外の場合。
            RuntimeError: 所有ノードまたはアトリビュートが無効の場合。
        """
        ...
    def __contains__(self, item: int | Plug) -> bool:
        """論理番号または要素Plugが、既存要素に含まれるかを返す。

        整数は論理番号として getIndices() と照合する(リスト上の位置ではない)。Plugは、このマルチアトリビュートの
        既存要素と同じ参照かを比べる。値は読み出さず、欠番を実体化しない。
        ``__len__`` は持たない(maya.cmdsが位置0〜len-1の並びとして展開し、論理番号と食い違う値を黙って返すため)。
        要素数は ``len(multi.getIndices())`` で求める。

        Args:
            item (int | Plug): 論理番号、または要素のPlug。

        Returns:
            bool: 既存要素に含まれる場合True。範囲外の番号・別のアトリビュートのPlugはFalse。

        Raises:
            TypeError: boolまたは整数・Plug以外の場合。
            RuntimeError: 所有ノードまたはアトリビュートが無効の場合。
        """
        ...
    def __iter__(self) -> Iterator[Plug]:
        """既存要素の参照一覧を取得し、論理番号順に反復する。

        反復子を作る時点のgetElements()を使い、欠番は列挙しない。要素値は読み出さない。

        Returns:
            Iterator[Plug]: 作成時に集めた要素参照の反復子。
        """
        ...
    def get(self, *, unit: str | None = ..., uiUnits: bool = ...) -> dict[int, object]:
        """既存要素の値を、論理番号をキーとするdictで取得する。

        getElements()の各要素でget()を呼ぶため、値取得に伴うDG評価が発生し得る。
        番号は詰め直さず、コンパウンドアトリビュートや配列型の要素値も平坦化しない。

        Args:
            unit (str | None): 各要素のgetへ渡す角度の単位。None(既定)は度、``"rad"`` はラジアン。
                uiUnits=Trueとは同時に指定できない。
            uiUnits (bool): 各要素のgetへ渡す。TrueはUI単位、既定Falseは角度が度、距離cm、時間秒。

        Returns:
            dict[int, object]: 新しいdict。値の型・単位は各要素のgetに従う。
                worldSpaceアトリビュートは、DAGインスタンス番号の要素も含む。

        Raises:
            TypeError: uiUnitsがbool以外、またはunitが文字列・None以外の場合。
            ValueError: unitが未対応の単位名、またはunitとuiUnits=Trueを同時に指定した場合。
            RuntimeError: 所有ノードまたはアトリビュートが無効、または要素値を取得できない場合。
        """
        ...
    def getElement(self, index: int) -> Plug:
        """論理番号の要素を、評価・実体化せず参照する(``multi[index]`` と同じ)。

        まだ存在しない要素(欠番)も参照を返し、その要素へのset/connectで作成される。
        参照の取得だけでは要素を作らない。存在する要素だけが必要なら :meth:`getElements`
        (既存要素の一覧)または ``index in multi`` (存在の判定)を使う。

        Args:
            index (int): 0〜2147483647の論理番号。

        Returns:
            Plug: 同じ所有Nodeを持つ新しい要素参照。

        Raises:
            TypeError: index未指定、boolまたは整数以外の場合。
            IndexError: 番号が0〜2147483647の範囲外の場合。
            RuntimeError: 所有ノードまたはアトリビュートが無効の場合。
        """
        ...
    def getElements(self) -> list[Plug]:
        """既存要素のPlugを、論理番号の昇順で取得する。

        getIndices()の番号だけを参照し、欠番を埋めず、要素値も読み出さない
        (未作成の要素も参照する :meth:`getElement` とは異なる)。
        worldSpaceアトリビュートは、評価前でもDAGインスタンス番号の要素を含む。

        Returns:
            list[Plug]: 新しいリストと要素ラッパー。所有Nodeは共有し、シーンを複製しない。

        Raises:
            RuntimeError: 所有ノードまたはアトリビュートが無効の場合。
        """
        ...
    def getNextAvailable(self, start: int = ..., asPlug: bool = ..., checkLocked: bool = ..., checkChildren: bool = ..., *, vacant: bool = ...) -> int | Plug:
        """次に使えるマルチアトリビュートの要素の論理番号(またはその要素Plug)を探す。要素の作成・予約はしない。

        既定(``vacant=False``)は ``cmds.connectAttr(nextAvailable=True)`` と同じ規則で、
        :meth:`Plug.connectTo` / :meth:`Plug.connect` の ``nextAvailable=True`` もこの結果へ接続する。
        要素は入力接続が無ければ使える(値を持つだけの要素・出力接続だけの要素も候補)。``start`` が負なら
        接続(子の接続を含む)のある最後の要素の次から探し、途中の空きは飛ばす。``checkLocked`` ならロック、
        ``checkChildren`` なら子(とそのマルチアトリビュート)の入力接続・ロックも避ける。

        ``vacant=True`` はMayaの規則とは別の「未使用の番号」の探索で、既存番号
        (``getExistingArrayAttributeIndices()``。値を持つ要素も含む)に無い最初の番号を探す。
        ``start`` が負なら0から。checkLocked/checkChildren は無視し、マルチアトリビュートのロックも例外にしない。
        worldSpaceのマルチアトリビュートのインスタンス番号補完(:meth:`getIndices`)も使わない。
        値を設定する空き要素を探す用途に使う。

        3つの探索規則の対比:

        .. list-table::
           :header-rows: 1

           * - 呼び方
             - 開始
             - 避けるもの
           * - ``getNextAvailable()``
             - 最後の接続要素の次(start<0)
             - 入力接続・ロック・子の入力
           * - ``getNextAvailable(vacant=True)``
             - 0(start<0)
             - 既存番号(値・接続のある要素)
           * - ``appendMessage(node)``
             - 最大番号+1
             - 既存番号すべて(穴は再利用しない)

        Args:
            start (int): 探索開始番号。負数は上記の既定開始位置。bool は受け付けない。
            asPlug (bool): Trueは番号の代わりにその要素Plugを返す。
            checkLocked (bool): ロックされた要素(とマルチアトリビュート全体のロック)を避ける。vacantでは無視。
            checkChildren (bool): コンパウンドアトリビュートの子とそのマルチアトリビュートも調べる。vacantでは無視。
            vacant (bool): Trueは既存番号(値・接続のある要素)に無い最初の番号を探す。

        Returns:
            int | Plug: 空き番号、または ``asPlug=True`` でその要素Plug。

        Raises:
            TypeError: startがboolまたは整数以外、asPlug/checkLocked/checkChildren/vacantがbool以外の場合。
            IndexError: startが上限(2147483647)を超える、または空きが無い場合。
            RuntimeError: 所有ノードまたはアトリビュートが無効、または ``vacant=False`` かつ
                ``checkLocked=True`` でマルチアトリビュート全体がロックされている場合。
        """
        ...
    def removeElement(self, index: int, *, fast: bool = ...) -> MultiPlug:
        """実体のあるマルチアトリビュートの要素を、接続を切断して削除する。

        OpenMayaの既存要素番号を対象とし、getIndices()によるworldSpaceの補完だけでは
        削除対象にしない。通常はcmds.removeMultiInstanceを使い、Undoが有効なら記録する。
        fastはMDGModifierで削除し、Undo設定を変更しない。

        Args:
            index (int): 削除する論理番号。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            MultiPlug: 自身。

        Raises:
            TypeError: indexがboolまたは整数以外の場合。
            IndexError: 論理番号が範囲外、または実体のある要素が存在しない場合。
            RuntimeError: 所有ノードまたはアトリビュートが無効、またはMayaが削除を拒否した場合。

        Note:
            デフォーマのターゲットはこの方法で除去しない。例えばblendShapeの ``weight`` の要素を
            消しても、エイリアスと ``inputTarget[].inputTargetGroup[i]`` が残る。blendShapeのターゲットは
            :meth:`mlib.nodes.BlendShape.removeTarget` で除去する。
        """
        ...
    def getSourceNodes(self) -> dict[int, Node]:
        """マルチアトリビュートの要素への接続元ノードを論理番号順に取得する。

        Returns:
            dict[int, Node]: 接続のある要素のみ。未接続の穴を維持して返す。
        """
        ...
    def appendMessage(self, node: str | Node, *, fast: bool = ...) -> int:
        """messageのマルチアトリビュートの最大番号の次へノード参照を追加する。

        Args:
            node (str | Node): 保存する参照。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            int: 追加した論理番号。途中の穴は再利用しない。
        """
        ...
    def getIndices(self) -> list[int]:
        """既存要素の論理番号を、値を評価せず昇順で取得する。

        疎な番号が[2, 10]なら[2, 10]を返し、物理的な列挙位置の[0, 1]へ詰め直さない。
        worldSpaceのマルチアトリビュートはOpenMayaの既存番号に全DAGインスタンスの0〜数-1を補完する
        (祖先による間接インスタンスを含む)。欠番を実体化せず、getElements()も同じ番号を使う。

        Returns:
            list[int]: 新しい論理番号リスト。

        Raises:
            RuntimeError: 所有ノードまたはアトリビュートが無効の場合。
        """
        ...
    @staticmethod
    def _validated_logical_index(index: int) -> int:
        """マルチアトリビュートの要素への参照・編集に使う論理番号を検証し、intで返す。

        Args:
            index (int): 対象要素の論理番号。``operator.index`` で整数へ変換できる値(boolを除く)。

        Returns:
            int: 検証済みの論理番号。

        Raises:
            TypeError: boolまたは整数以外の場合。
            IndexError: 0〜2147483647の範囲外の場合。
        """
        ...
    def _element_at(self, index: int) -> Plug:
        """書込み・接続用の参照のみを取得し、欠番の要素を作成しない。

        Args:
            index (int): 論理番号。

        Returns:
            Plug: 型付き参照。危険な内部データ型の未作成要素は拒否する。
        """
        ...
