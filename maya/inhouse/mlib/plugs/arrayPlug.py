"""配列アトリビュートの論理インデックスと要素プラグを扱う。"""

from contextlib import nullcontext

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from ..core.attributeType import is_internal_data_type
from ..decorator import undoChunk
from ..util import _ArgumentError, _UNSET
from .plug import Plug, _instance_count


class ArrayPlug(Plug):
    """multiアトリビュート全体の参照を保持し、疎な要素番号と要素Plugを扱う。

    doubleArray等の「一つのPlugに配列データを格納する型」とは異なり、各要素が
    独立した論理番号を持つ。角括弧は論理番号、反復は既存要素の参照、get()は値の取得。
    欠番の参照取得だけでは要素を作成せず、要素へのset/connectで実体化する。

    maya.cmdsはArrayPlug自体をシーケンスとして展開しようとして失敗するため、
    配列全体を渡すときは ``str(array_plug)`` または ``array_plug.getFullName()`` を使う。
    配列要素も複合Plugなら文字列化する。mlibのコマンドにはそのまま渡せる。
    """

    def __getitem__(self, index):
        """論理番号を指定し、既存または未作成の配列要素を参照する。

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
        self._require_valid()
        index = self._validate_index(index)
        return Plug(self._node, self._mplug.elementByLogicalIndex(index))

    def __iter__(self):
        """既存要素の参照一覧を取得し、論理番号順に反復する。

        反復子を作る時点のgetElements()を使い、欠番は列挙しない。要素値は読み出さない。

        Returns:
            Iterator[Plug]: 作成時に集めた要素参照の反復子。
        """
        return iter(self.getElements())

    def get(self, *, uiUnits=False):
        """既存要素の値を、論理番号をキーとするdictで取得する。

        getElements()の各要素でget()を呼ぶため、値取得に伴うDG評価が発生し得る。
        番号は詰め直さず、複合型や配列型の要素値も平坦化しない。

        Args:
            uiUnits (bool): 各要素のgetへ渡す。TrueはUI単位、既定Falseは内部単位。

        Returns:
            dict[int, object]: 新しいdict。値の型・単位は各要素のgetに従う。
                worldSpaceアトリビュートは、DAGインスタンス番号の要素も含む。

        Raises:
            TypeError: uiUnitsがbool以外の場合。
            RuntimeError: 所有ノードまたはアトリビュートが無効、または要素値を取得できない場合。
        """
        self._validate_ui_units(uiUnits)
        return {plug.mplug().logicalIndex(): plug.get(uiUnits=uiUnits) for plug in self.getElements()}

    def set(self, value, safe=False, *, uiUnits=False, fast=False):
        """array プラグへの直接の値設定を禁止する。

        Args:
            value (object): 設定要求値。内容に関係なく拒否する。
            safe (bool): Plug共通の引数。Trueでも配列全体への値設定は許可しない。
            uiUnits (bool): TrueはUI単位の数値。既定Falseは内部単位。
            fast (bool): Plug共通インターフェースの引数。値にかかわらず配列全体への設定を拒否する。

        Returns:
            NoReturn: 必ず TypeError を送出する。

        Raises:
            TypeError: 常に送出される。要素プラグへ設定すること。

        fastにかかわらず要素Plugのset()を使用する。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        raise TypeError("Set an array element instead of the array plug")

    def getElement(self, index=_UNSET, *, idx=_UNSET):
        """既存の論理インデックスの要素Plugを、評価や実体化なしで取得する。

        worldMatrix等は、評価前でもDAGインスタンス番号の要素を参照できる。
        未存在の参照にはarray[index]を使い、set/connectで要素を作成する。

        Args:
            index (int): 論理インデックス。別名idx。
            idx (int): indexの別名。同時指定は不可。

        Returns:
            Plug: 既存要素の参照。

        Raises:
            TypeError: indexがboolまたは整数以外の場合。
            IndexError: 要素が存在しない、または0〜2147483647の範囲外の場合。
            RuntimeError: 所有ノードまたはアトリビュートが無効の場合。
        """
        if idx is not _UNSET:
            if index is not _UNSET:
                raise _ArgumentError("Specify only one of 'index' and 'idx'")
            index = idx
        if index is _UNSET:
            raise _ArgumentError("Missing required argument: 'index'")
        self._require_valid()
        index = self._validate_index(index)
        if index not in self.getIndices():
            raise IndexError(f"No element at logical index {index} on {self.getFullName()}")
        return self[index]

    def getElements(self):
        """既存要素のPlugを、論理番号の昇順で取得する。

        getIndices()の番号だけを参照し、欠番を埋めず、要素値も読み出さない。
        worldSpaceアトリビュートは、評価前でもDAGインスタンス番号の要素を含む。

        Returns:
            list[Plug]: 新しいリストと要素ラッパー。所有Nodeは共有し、シーンを複製しない。

        Raises:
            RuntimeError: 所有ノードまたはアトリビュートが無効の場合。
        """
        # 要素ごとに存在を確かめ直さず、既存の番号から直接 Plug を作る。
        return [Plug(self._node, self._mplug.elementByLogicalIndex(index))
                for index in self.getIndices()]

    def getNextAvailableIndex(self, start=0):
        """OpenMayaの既存要素番号に含まれない最初の候補番号を探す。

        ``getExistingArrayAttributeIndices()`` だけを調べ、getIndices()が補完する
        worldSpaceのDAGインスタンス番号は含めない。ロックや子の入力接続も調べないため、
        connect(nextAvailable=True)が選ぶ接続先とは異なる。要素の作成・予約はしない。

        Args:
            start (int): 探索開始番号。負数だけを検証し、整数型や上限は検証しない。

        Returns:
            int: start以上で既存番号に含まれない最初の候補。
                角括弧等で受理される論理番号の範囲内とは限らない。

        Raises:
            ValueError: startが負の場合。
            RuntimeError: 所有ノードまたはアトリビュートが無効の場合。
        """
        if start < 0:
            raise ValueError("start must be >= 0")
        self._require_valid()
        existing = set(self._mplug.getExistingArrayAttributeIndices())
        index = start
        while index in existing:
            index += 1
        return index

    def removeElement(self, index=_UNSET, *, fast=False, idx=_UNSET):
        """実体のある配列要素を、接続を切断して削除する。

        OpenMayaの既存要素番号を対象とし、getIndices()によるworldSpaceの補完だけでは
        削除対象にしない。通常はcmds.removeMultiInstanceを使い、Undoが有効なら記録する。
        fastはMDGModifierで削除し、Undo設定を変更しない。

        Args:
            index (int): 削除する論理番号。別名 ``idx`` も使用可能。
            fast (bool): TrueはUndoなしのOpenMaya直接更新。
            idx (int): indexの別名。同時指定は不可。

        Returns:
            ArrayPlug: 自身。

        Raises:
            TypeError: indexがboolまたは整数以外の場合。
            IndexError: 論理番号が範囲外、または実体のある要素が存在しない場合。
            RuntimeError: 所有ノードまたはアトリビュートが無効、またはMayaが削除を拒否した場合。
        """
        if idx is not _UNSET:
            if index is not _UNSET:
                raise _ArgumentError("Specify only one of 'index' and 'idx'")
            index = idx
        if index is _UNSET:
            raise _ArgumentError("Missing required argument: 'index'")
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibArrayPlugRemoveElement"):
            self._require_valid()
            index = self._validate_index(index)
            if index not in self._mplug.getExistingArrayAttributeIndices():
                raise IndexError(f"No element at logical index {index} on {self.getFullName()}")
            if fast:
                modifier = om2.MDGModifier()
                modifier.removeMultiInstance(self._mplug.elementByLogicalIndex(index), True)
                modifier.doIt()
            else:
                cmds.removeMultiInstance(f"{self.getFullName()}[{index}]", b=True)
            return self

    def getSourceNodes(self):
        """配列要素への接続元ノードを論理インデックス順に取得する。

        Returns:
            dict[int, Node]: 接続のある要素のみ。未接続の穴を維持して返す。
        """
        result = {}
        for element in self.getElements():
            source = element.getSource(skipConversionNodes=False)
            if source is not None:
                result[element.mplug().logicalIndex()] = source.getNode()
        return result

    def appendMessage(self, node, *, fast=False):
        """message配列の最大インデックスの次へノード参照を追加する。

        Args:
            node (str | Node): 保存する参照。
            fast (bool): TrueはUndoなしのOpenMaya直接更新。

        Returns:
            int: 追加した論理インデックス。途中の穴は再利用しない。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlib.ArrayPlug.appendMessage"):
            from .plug import MAX_LOGICAL_INDEX
            from ..nodes.node import Node
            self._require_valid()
            if not self._mplug.attribute().hasFn(om2.MFn.kMessageAttribute):
                raise TypeError("Expected a message array")
            index = max(self.getIndices(), default=-1) + 1
            if index > MAX_LOGICAL_INDEX:
                raise IndexError("Message array index limit reached")
            Node(node).getPlug("message").connectTo(self._element_reference(index), fast=fast)
            return index

    def getIndices(self):
        """既存要素の論理番号を、値を読み出さず昇順で取得する。

        例えば要素番号が[2, 10]なら[2, 10]を返し、物理的な列挙位置の[0, 1]は返さない。
        ``getExistingArrayAttributeIndices()`` の番号に加え、worldMatrix等のworldSpace
        アトリビュートでは、所有DAGノードの全インスタンス番号を補完する。
        要素を評価するまでOpenMayaの既存番号に現れない場合があるため。
        補完範囲は0〜インスタンス数-1で、祖先による間接インスタンスも含む。
        番号の取得では、値の評価や欠番の実体化を行わない。

        Returns:
            list[int]: 新しい論理番号リスト。getElements()も同じ番号を使う。

        Raises:
            RuntimeError: 所有ノードまたはアトリビュートが無効の場合。
        """
        self._require_valid()
        indices = list(self._mplug.getExistingArrayAttributeIndices())
        count = _instance_count(self._mplug)
        if count:
            indices = sorted(set(indices).union(range(count)))
        return indices

    @staticmethod
    def _validate_index(index):
        """配列要素への参照・編集に使う論理番号を検証する。

        Args:
            index (int): 対象要素の論理番号。探索開始番号の検証には使わない。

        Returns:
            int: 変換せずに返す検証済み番号。

        Raises:
            TypeError: boolまたは整数以外の場合。
            IndexError: 0〜2147483647の範囲外の場合。
        """
        from .plug import MAX_LOGICAL_INDEX
        if isinstance(index, bool) or not isinstance(index, int):
            raise TypeError("Logical index must be an integer")
        if not 0 <= index <= MAX_LOGICAL_INDEX:
            raise IndexError("Logical index must be in 0..2147483647")
        return index

    def _element_reference(self, index):
        """書込み・接続用の参照のみを取得し、欠番の要素を作成しない。

        Args:
            index (int): 論理番号。

        Returns:
            Plug: 型付き参照。危険な内部データ型の未作成要素は拒否する。
        """
        self._require_valid()
        index = self._validate_index(index)
        mplug = self._mplug.elementByLogicalIndex(index)
        if is_internal_data_type(mplug) and index not in self._mplug.getExistingArrayAttributeIndices():
            raise RuntimeError("Cannot create an internal data element: " + self.getFullName())
        return Plug(self._node, mplug)
