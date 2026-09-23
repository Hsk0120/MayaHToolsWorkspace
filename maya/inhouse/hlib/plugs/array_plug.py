"""配列属性の論理インデックスと要素プラグを扱う。"""

import maya.cmds as cmds

from ..decorators.undo import undo_chunk
from .plug import Plug


class ArrayPlug(Plug):
    """multi（array）属性用の Plug。"""

    def get(self, ws=False):
        """既存インデックスをキーにした要素値の dict を返す。

        Args:
            ws (bool): 配列自身では空間変換を行わないため無視される。

        Returns:
            dict[int, object]: 論理インデックスをキーとする要素値。
        """
        return {index: self.element(index).get() for index in self._mplug.getExistingArrayAttributeIndices()}

    def set(self, value):
        """array プラグへの直接の値設定を禁止する。

        Args:
            value (object): 設定要求値。内容に関係なく拒否する。

        Returns:
            NoReturn: 必ず TypeError を送出する。

        Raises:
            TypeError: 常に送出される。要素プラグへ設定すること。
        """
        raise TypeError("Set an array element instead of the array plug")

    def element(self, index, create=False):
        """論理インデックスの要素プラグを取得する。

        Args:
            index (int): 論理インデックス。
            create (bool): 存在しない要素も作成対象として取得するか。

        Returns:
            Plug: 要素プラグ。

        Raises:
            IndexError: create が ``False`` で要素が存在しない場合。
        """
        existing_indices = self._mplug.getExistingArrayAttributeIndices()
        if not create and index not in existing_indices:
            raise IndexError(f"No element at logical index {index} on {self.full_name}")
        mplug = self._mplug.elementByLogicalIndex(index)
        return Plug(self._node, mplug)

    def elements(self):
        """存在する要素プラグをすべて取得する。

        Returns:
            list[Plug]: 既存要素。
        """
        return [self.element(index) for index in self._mplug.getExistingArrayAttributeIndices()]

    def next_available(self, start=0):
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
        """
        if start < 0:
            raise ValueError("start must be >= 0")
        existing = set(self._mplug.getExistingArrayAttributeIndices())
        index = start
        while index in existing:
            index += 1
        return index

    @undo_chunk("hlibArrayPlugAddElement")
    def add_element(self):
        """次の空きインデックス(next_available())へ要素を作成して返す。

        Returns:
            Plug: 作成した要素プラグ。
        """
        return self.element(self.next_available(), create=True)

    @undo_chunk("hlibArrayPlugRemoveElement")
    def remove_element(self, index):
        """指定した論理インデックスの要素を削除する。

        Args:
            index (int): 削除する論理インデックス。

        Returns:
            ArrayPlug: 自身。

        Raises:
            IndexError: 指定したインデックスに要素が存在しない場合。
            RuntimeError: Maya が削除を拒否した場合。
        """
        if index not in self._mplug.getExistingArrayAttributeIndices():
            raise IndexError(f"No element at logical index {index} on {self.full_name}")
        cmds.removeMultiInstance(f"{self.full_name}[{index}]", b=True)
        return self

    def __getitem__(self, index):
        """論理インデックスの要素プラグを取得する。

        Args:
            index (int): 論理インデックス。

        Returns:
            Plug: 対応する要素プラグ。

        Raises:
            IndexError: 指定した論理インデックスが存在しない場合。
        """
        return self.element(index)
