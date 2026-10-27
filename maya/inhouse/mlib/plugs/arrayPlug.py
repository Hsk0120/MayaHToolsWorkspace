"""配列アトリビュートの論理インデックスと要素プラグを扱う。"""

from contextlib import nullcontext

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from ..core.attributeType import _convert_units, is_internal_data_type, value_reader
from ..decorator import undoChunk
from ..util import _ArgumentError, _UNSET
from .plug import MAX_LOGICAL_INDEX, Plug, _instance_count


class ArrayPlug(Plug):
    """multiアトリビュート全体を参照し、疎な論理番号と要素Plugを扱う。

    doubleArray等の単一Plugの配列データとは異なる。``array[index]`` は論理番号の
    参照、反復は既存要素、get()は値の取得。欠番は参照だけでは作られず、set/connectで実体化する。
    maya.cmdsへは ``str(array)`` で渡す。要素が複合Plugの場合も文字列化し、mlib.selectにはそのまま渡せる。
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
        if type(self).getElements is not ArrayPlug.getElements:
            return {plug.mplug().logicalIndex(): plug.get(uiUnits=uiUnits) for plug in self.getElements()}
        indices = self.getIndices()
        if not indices:
            return {}
        # 要素は同じアトリビュート定義を共有するため、ラッパーの型と読取関数は全要素で同じになる。
        # 基底Plugの読取(get/_get_internal)をそのまま使う型に限り、2個目以降のラッパー作成を省いて
        # 同じ手順(有効性の確認→読取関数→単位換算)で読む。それ以外は従来どおり要素ごとのget。
        mplug = self._mplug
        first = Plug(self._node, mplug.elementByLogicalIndex(indices[0]))
        element_class = type(first)
        reader = None
        if (element_class.get is Plug.get and element_class._get_internal is Plug._get_internal
                and element_class._require_valid is Plug._require_valid):
            first._require_valid()
            reader = first._reader
            if reader is None:
                reader = first._reader = value_reader(first._attribute)
        if not reader:
            elements = [first] + [Plug(self._node, mplug.elementByLogicalIndex(index)) for index in indices[1:]]
            return {plug.mplug().logicalIndex(): plug.get(uiUnits=uiUnits) for plug in elements}
        result = {}
        for index in indices:
            element = mplug.elementByLogicalIndex(index)
            first._require_valid()
            value = reader(element)
            result[element.logicalIndex()] = _convert_units(element, value) if uiUnits else value
        return result

    def set(self, value, safe=False, *, uiUnits=False, fast=False):
        """配列全体への値設定を拒否する。各要素のset()を使う。

        Args:
            value (object): 内容にかかわらず拒否する設定要求値。
            safe (bool): Trueでも拒否を抑制しない。
            uiUnits (bool): Plug共通の単位指定。全体設定は許可しない。
            fast (bool): Plug共通の経路指定。全体設定は許可しない。

        Returns:
            NoReturn: 必ずTypeErrorを送出する。

        Raises:
            TypeError: fastがbool以外の場合、および配列全体への設定要求。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        raise TypeError("Set an array element instead of the array plug")

    def getElement(self, index=_UNSET, *, idx=_UNSET):
        """既存の論理番号の要素を、評価・実体化せず参照する。

        worldSpace配列は評価前のDAGインスタンス番号も既存として扱う。
        欠番の参照には ``array[index]``、作成にはその要素のset/connectを使う。

        Args:
            index (int): 0〜2147483647の論理番号。短縮名idx。
            idx (int): indexの別名。同時指定は不可。

        Returns:
            Plug: 同じ所有Nodeを持つ新しい要素参照。

        Raises:
            TypeError: index未指定、長短名の同時指定、boolまたは整数以外の場合。
            IndexError: 要素が存在しない、または番号が範囲外の場合。
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

    def getNextAvailable(self, start=-1, asPlug=False, checkLocked=True, checkChildren=True, *, vacant=False):
        """次に使える配列要素の論理番号(またはその要素Plug)を探す。要素の作成・予約はしない。

        既定(``vacant=False``)は入力接続できる要素を探す。``start`` が負なら最後の接続要素の次
        (途中の空きは飛ばす)から、入力接続と、``checkLocked`` ならロック、``checkChildren`` なら
        子(とその配列)の入力接続・ロックも避けた最初の番号を返す。値を持つだけの既存要素や出力接続
        だけの要素は候補になる。

        ``vacant=True`` は既存番号(``getExistingArrayAttributeIndices()``)に無い最初の番号を探す。
        ``start`` が負なら0から。checkLocked/checkChildren は無視し、配列のロックも例外にしない。
        worldSpace配列のインスタンス番号補完(:meth:`getIndices`)も使わない。

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
            checkLocked (bool): ロックされた要素(と配列全体のロック)を避ける。vacantでは無視。
            checkChildren (bool): 複合の子とその配列も調べる。vacantでは無視。
            vacant (bool): Trueは既存番号(値・接続のある要素)に無い最初の番号を探す。

        Returns:
            int | Plug: 空き番号、または ``asPlug=True`` でその要素Plug。

        Raises:
            TypeError: startがboolまたは整数以外、asPlug/checkLocked/checkChildren/vacantがbool以外の場合。
            IndexError: startが上限(2147483647)を超える、または空きが無い場合。
            RuntimeError: 所有ノードまたはアトリビュートが無効、または ``vacant=False`` かつ
                ``checkLocked=True`` で配列全体がロックされている場合。
        """
        for name, flag in (("asPlug", asPlug), ("checkLocked", checkLocked),
                           ("checkChildren", checkChildren), ("vacant", vacant)):
            if not isinstance(flag, bool):
                raise TypeError("{} must be a bool".format(name))
        if isinstance(start, bool) or not isinstance(start, int):
            raise TypeError("start must be an integer")
        self._require_valid()
        mp = self._mplug
        if vacant:
            existing = set(mp.getExistingArrayAttributeIndices())
            index = self._validate_index(max(start, 0))
            while index in existing:
                index += 1
            if index > MAX_LOGICAL_INDEX:
                raise IndexError("No available array index")
            return Plug(self._node, mp.elementByLogicalIndex(index)) if asPlug else index
        if checkLocked and mp.isLocked:
            raise RuntimeError("Array is locked: " + self.getFullName())
        if start < 0:
            count = mp.numConnectedElements()
            start = mp.connectionByPhysicalIndex(count - 1).logicalIndex() + 1 if count else 0
        index = self._validate_index(start)

        def occupied(value):
            """子階層を含む入力とロックを確認する。"""
            if value.isDestination or (checkLocked and value.isLocked):
                return True
            if checkChildren:
                if value.isArray:
                    return any(occupied(value.elementByLogicalIndex(i))
                               for i in value.getExistingArrayAttributeIndices())
                if value.isCompound:
                    return any(occupied(value.child(i)) for i in range(value.numChildren()))
            return False
        while index <= MAX_LOGICAL_INDEX:
            candidate = mp.elementByLogicalIndex(index)
            if not occupied(candidate):
                return Plug(self._node, candidate) if asPlug else index
            index += 1
        raise IndexError("No available array index")

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
            # 循環import(nodes → plugs)を避けるため、使う時点で読み込む。
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
        """既存要素の論理番号を、値を評価せず昇順で取得する。

        疎な番号が[2, 10]なら[2, 10]を返し、物理的な列挙位置の[0, 1]へ詰め直さない。
        worldSpace配列はOpenMayaの既存番号に全DAGインスタンスの0〜数-1を補完する
        （祖先による間接インスタンスを含む）。欠番を実体化せず、getElements()も同じ番号を使う。

        Returns:
            list[int]: 新しい論理番号リスト。

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
