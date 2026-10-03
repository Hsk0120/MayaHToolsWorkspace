"""配列アトリビュートの論理インデックスと要素プラグを扱う。"""

from ..decorators._fast import fast_edit, is_fast

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from .._core.attributeType import is_internal_data_type
from ..decorators.undo import undoChunk
from .plug import Plug, _instance_count


class ArrayPlug(Plug):
    """multi（array）アトリビュート用の Plug。

    ``array_plug[index]`` で論理インデックスの要素 Plug を取得できる。この
    ``__getitem__`` があるため、maya.cmds は ArrayPlug オブジェクト自体を
    シーケンスとして展開しようとして失敗する(``cmds.getAttr(array_plug)`` は不可)。
    配列アトリビュート全体を maya.cmds へ渡す場合は ``str(array_plug)`` または
    ``array_plug.fullName()`` を渡す。要素 Plug(``array_plug[0]``)と、
    hlib のコマンド(``hlib.select`` など)は ArrayPlug をそのまま受け付ける。"""

    def _existing_indices(self):
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

    def get(self):
        """既存インデックスをキーにした要素値の dict を返す。

        Returns:
            dict[int, object]: 論理インデックスをキーとする要素値。ワールド空間アトリビュートは
                インスタンス番号の要素も含む。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        return {plug.mplug().logicalIndex(): plug.get() for plug in self.elements()}

    @fast_edit
    def set(self, value, *, fast=False):
        """array プラグへの直接の値設定を禁止する。

        Args:
            fast (bool): Plug共通インターフェースの引数。値にかかわらず配列全体への設定を拒否する。
            value (object): 設定要求値。内容に関係なく拒否する。

        Returns:
            NoReturn: 必ず TypeError を送出する。

        Raises:
            TypeError: 常に送出される。要素プラグへ設定すること。

        fastにかかわらず要素Plugのset()を使用する。
        """
        raise TypeError("Set an array element instead of the array plug")

    @staticmethod
    def _validate_index(index):
        """Mayaの論理番号を検証する。範囲外はIndexError、型不正はTypeError。"""
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
            raise RuntimeError("Cannot create an internal data element: " + self.fullName())
        return Plug(self._node, mplug)

    def element(self, index, create=False):
        """論理インデックスの要素プラグを取得する。

        ``worldMatrix`` などのワールド空間アトリビュートは、所有 DAG ノードのインスタンス番号の
        要素を評価前でも取得できる(作成直後のノードの ``worldMatrix[0]`` など)。

        Args:
            index (int): 論理インデックス。
            create (bool): True の場合、データを持つ要素が無ければ Maya 上に要素を
                作成してから返す(``cmds.getAttr`` の問い合わせで作成するため Undo 対象外)。
                fast更新の内部では参照だけを取得し、値の書込み時に要素を作成する。
                ただし ``message`` 型のように値を持たないアトリビュートの配列では要素を作成できない。
                この場合も要素プラグは返すため接続先・接続元に使え、要素は接続した時点で
                存在するようになる(それまで ``elements()`` や ``nextAvailableIndex()`` には現れない)。

        Returns:
            Plug: 要素プラグ。

        Raises:
            TypeError: indexがboolまたは整数以外の場合。
            IndexError: create が ``False`` で要素が存在しない場合。index が 0〜2147483647
                (``MPlug.logicalIndex()`` の範囲)の外の場合(``elementByLogicalIndex()`` は
                範囲外の番号を別の番号へ変換し、maya.cmds は 2147483647 に切り詰めるため、
                別の要素を返したり作成したりしない)。
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
                create が ``True`` で、Maya 内部のデータ型(nurbsSurface の ``patchUVIds``
                など。:func:`hlib._core.attributeType.is_internal_data_type`)の配列の場合
                (要素を問い合わせると Maya が異常終了する場合があるため作成しない)。
        """
        self._require_valid()
        index = self._validate_index(index)
        mplug = self._mplug.elementByLogicalIndex(index)
        if index not in self._mplug.getExistingArrayAttributeIndices():
            if create:
                if is_internal_data_type(mplug):
                    raise RuntimeError(
                        f"Maya 内部のデータ型の配列には要素を作成できません: {self.fullName()}"
                    )
                # maya.cmds は存在しない要素を問い合わせると要素を作成する。Plug の生成
                # (アトリビュート型の判定)は maya.cmds へ問い合わせず要素を作らないため、ここで作成する。
                # fast更新はこの参照へ値を書く時に要素を実体化する。
                # 型照会のためのコマンド評価・名前の再解決を挟まない。
                if not is_fast():
                    cmds.getAttr(f"{self.fullName()}[{index}]", type=True)
            elif index not in self._existing_indices():
                raise IndexError(f"No element at logical index {index} on {self.fullName()}")
        return Plug(self._node, mplug)

    def elements(self):
        """存在する要素プラグをすべて取得する。

        Returns:
            list[Plug]: 既存要素。ワールド空間アトリビュートはインスタンス番号の要素も含む。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        # 要素ごとに存在を確かめ直さず、既存の番号から直接 Plug を作る。
        return [Plug(self._node, self._mplug.elementByLogicalIndex(index))
                for index in self._existing_indices()]

    def nextAvailableIndex(self, start=0):
        """接続・データを持つ要素が存在しない論理インデックスを探す。

        cymel の同名メソッドとは異なり、ロック状態や子要素の再帰チェックは行わない
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

    @undoChunk("hlibArrayPlugAddElement")
    def addElement(self):
        """次の空きインデックス(nextAvailableIndex())へ要素への参照を返す。

        通常は element(create=True) で実体化する。fast 更新の内部では値の書き込みまで
        実体化を遅延する。

        ``message`` 型のように値を持たないアトリビュートの配列では要素を作成できないため
        (:meth:`element` 参照)、返した要素へ接続するまでは、呼び出すたびに同じ
        インデックスの要素プラグを返す。

        Returns:
            Plug: 要素プラグ。
        """
        return self.element(self.nextAvailableIndex(), create=True)

    @undoChunk("hlibArrayPlugRemoveElement")
    def removeElement(self, index):
        """指定した論理インデックスの要素を削除する。

        Args:
            index (int): 削除する論理インデックス。

        Returns:
            ArrayPlug: 自身。

        Raises:
            IndexError: 指定したインデックスに要素が存在しない場合。
            RuntimeError: 所有ノードが無効(削除済み)、アトリビュートが削除済み、または Maya が削除を拒否した場合。
        """
        self._require_valid()
        if index not in self._mplug.getExistingArrayAttributeIndices():
            raise IndexError(f"No element at logical index {index} on {self.fullName()}")
        cmds.removeMultiInstance(f"{self.fullName()}[{index}]", b=True)
        return self

    def __getitem__(self, index):
        """論理インデックスの要素プラグを取得する。

        ``__len__``/``__iter__`` は持たない。``for`` 文は Python の旧来の
        シーケンス規約で 0 から順に取得し、最初の欠番で止まるため、既存要素の
        列挙には :meth:`elements` を使う。

        Args:
            index (int): 論理インデックス。

        Returns:
            Plug: 対応する要素プラグ。

        Raises:
            IndexError: 指定した論理インデックスが存在しない場合(0〜2147483647 の範囲外を含む)。
        """
        return self.element(index)

    def sourceNodes(self):
        """配列要素への接続元ノードを論理インデックス順に取得する。

        Returns:
            dict[int, Node]: 接続のある要素のみ。未接続の穴を維持して返す。
        """
        result = {}
        for element in self.elements():
            source = element.source()
            if source is not None:
                result[element.mplug().logicalIndex()] = source.node
        return result

    @undoChunk("hlib.ArrayPlug.appendMessage")
    def appendMessage(self, node):
        """message配列の最大インデックスの次へノード参照を追加する。

        Args:
            node (str | Node): 保存する参照。

        Returns:
            int: 追加した論理インデックス。途中の穴は再利用しない。
        """
        from ..plugs.plug import MAX_LOGICAL_INDEX
        from ..nodes.node import Node
        self._require_valid()
        if not self._mplug.attribute().hasFn(om2.MFn.kMessageAttribute):
            raise TypeError("Expected a message array")
        index = max(self._existing_indices(), default=-1) + 1
        if index > MAX_LOGICAL_INDEX:
            raise IndexError("Message array index limit reached")
        Node(node).plug("message").connect(self._element_reference(index))
        return index
