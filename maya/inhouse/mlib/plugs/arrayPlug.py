"""配列アトリビュートの論理インデックスと要素プラグを扱う。"""

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from ..core.attributeType import is_internal_data_type
from ..decorator import _flag_aliases, _fast_edit, _is_fast, _safe_edit, undoChunk
from .plug import Plug, _instance_count


class ArrayPlug(Plug):
    """multi（array）アトリビュート用の Plug。

    ``array_plug[index]`` で論理インデックスの要素 Plug を取得できる。この
    ``__getitem__`` があるため、maya.cmds は ArrayPlug オブジェクト自体を
    シーケンスとして展開しようとして失敗する(``cmds.getAttr(array_plug)`` は不可)。
    配列アトリビュート全体を maya.cmds へ渡す場合は ``str(array_plug)`` または
    ``array_plug.getFullName()`` を渡す。要素 Plug(``array_plug[0]``)と、
    mlib のコマンド(``mlib.select`` など)は ArrayPlug をそのまま受け付ける。"""

    def __getitem__(self, index):
        """論理インデックスの要素プラグを取得する。

        未作成の番号も参照できる。取得だけでは要素を実体化せず、set/connect時に作成する。
        反復は既存要素だけを論理番号順に返す。

        Args:
            index (int): 論理インデックス。

        Returns:
            Plug: 対応する要素プラグ。

        Raises:
            IndexError: 論理インデックスが0〜2147483647の範囲外の場合。
        """
        self._require_valid()
        index = self._validate_index(index)
        return Plug(self._node, self._mplug.elementByLogicalIndex(index))

    def __iter__(self):
        """既存要素を論理番号順で反復する。

        Returns:
            Iterator[Plug]: 未作成の番号へ進まない既存要素の反復子。
        """
        return iter(self.getElements())

    def get(self, *, uiUnits=False):
        """既存インデックスをキーにした要素値の dict を返す。

        Args:
            uiUnits (bool): TrueはUI単位の数値。既定Falseは内部単位。

        Returns:
            dict[int, object]: 論理インデックスをキーとする要素値。ワールド空間アトリビュートは
                インスタンス番号の要素も含む。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        self._validate_ui_units(uiUnits)
        return {plug.mplug().logicalIndex(): plug.get(uiUnits=uiUnits) for plug in self.getElements()}

    @_fast_edit
    @_safe_edit
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
        raise TypeError("Set an array element instead of the array plug")

    @_flag_aliases(idx="index")
    def getElement(self, index):
        """既存の論理インデックスの要素Plugを、評価や実体化なしで取得する。

        worldMatrix等は、評価前でもDAGインスタンス番号の要素を参照できる。
        未存在の参照にはarray[index]を使い、set/connectで要素を作成する。

        Args:
            index (int): 論理インデックス。別名idx。

        Returns:
            Plug: 既存要素の参照。

        Raises:
            TypeError: indexがboolまたは整数以外の場合。
            IndexError: 要素が存在しない、または0〜2147483647の範囲外の場合。
            RuntimeError: 所有ノードまたはアトリビュートが無効の場合。
        """
        self._require_valid()
        index = self._validate_index(index)
        if index not in self.getIndices():
            raise IndexError(f"No element at logical index {index} on {self.getFullName()}")
        return self[index]

    def getElements(self):
        """存在する要素プラグをすべて取得する。

        Returns:
            list[Plug]: 既存要素。ワールド空間アトリビュートはインスタンス番号の要素も含む。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        # 要素ごとに存在を確かめ直さず、既存の番号から直接 Plug を作る。
        return [Plug(self._node, self._mplug.elementByLogicalIndex(index))
                for index in self.getIndices()]

    def getNextAvailableIndex(self, start=0):
        """接続・データを持つ要素が存在しない論理インデックスを探す。

        ロック状態や子要素の再帰チェックは行わない
        単純な実装で、``getExistingArrayAttributeIndices()`` に含まれない
        最初のインデックスを返す。

        Args:
            start (int): 探索を開始する論理インデックス。

        Returns:
            int: start 以上で最初に存在しない論理インデックス。

        Raises:
            ValueError: start が負の場合。
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        if start < 0:
            raise ValueError("start must be >= 0")
        self._require_valid()
        existing = set(self._mplug.getExistingArrayAttributeIndices())
        index = start
        while index in existing:
            index += 1
        return index

    @_flag_aliases(idx="index")
    @_fast_edit
    @undoChunk("mlibArrayPlugRemoveElement")
    def removeElement(self, index, *, fast=False):
        """指定した論理インデックスの要素を削除する。

        Args:
            index (int): 削除する論理インデックス。 別名 ``idx`` も使用可能。
            fast (bool): TrueはUndoなしのOpenMaya直接更新。

        Returns:
            ArrayPlug: 自身。

        Raises:
            IndexError: 指定したインデックスに要素が存在しない場合。
            RuntimeError: 所有ノードが無効(削除済み)、アトリビュートが削除済み、または Maya が削除を拒否した場合。
        """
        self._require_valid()
        index = self._validate_index(index)
        if index not in self._mplug.getExistingArrayAttributeIndices():
            raise IndexError(f"No element at logical index {index} on {self.getFullName()}")
        if _is_fast():
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

    @_fast_edit
    @undoChunk("mlib.ArrayPlug.appendMessage")
    def appendMessage(self, node, *, fast=False):
        """message配列の最大インデックスの次へノード参照を追加する。

        Args:
            node (str | Node): 保存する参照。
            fast (bool): TrueはUndoなしのOpenMaya直接更新。

        Returns:
            int: 追加した論理インデックス。途中の穴は再利用しない。
        """
        from .plug import MAX_LOGICAL_INDEX
        from ..nodes.node import Node
        self._require_valid()
        if not self._mplug.attribute().hasFn(om2.MFn.kMessageAttribute):
            raise TypeError("Expected a message array")
        index = max(self.getIndices(), default=-1) + 1
        if index > MAX_LOGICAL_INDEX:
            raise IndexError("Message array index limit reached")
        Node(node).getPlug("message").connectTo(self._element_reference(index))
        return index

    def getIndices(self):
        """存在する要素の論理インデックスを昇順で返す。

        データを持つ要素(``getExistingArrayAttributeIndices()``)に加え、
        ``worldMatrix`` などのワールド空間アトリビュートでは、所有 DAG ノードのインスタンス番号
        (0～インスタンス数-1)も存在する要素として扱う。ワールド空間アトリビュートの要素は
        評価されるまでデータを持たず、作成直後のノードでは一覧に現れないため。
        インスタンス数には、インスタンス化された祖先による間接インスタンスも含める
        (``MDagPath.instanceNumber()`` と同じ数え方)。

        Returns:
            list[int]: 論理インデックス。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        self._require_valid()
        indices = list(self._mplug.getExistingArrayAttributeIndices())
        count = _instance_count(self._mplug)
        if count:
            indices = sorted(set(indices).union(range(count)))
        return indices

    @staticmethod
    def _validate_index(index):
        """Mayaの論理番号を検証する。範囲外はIndexError、型不正はTypeError。

        Args:
            index: 対象要素の番号または探索開始番号。
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
