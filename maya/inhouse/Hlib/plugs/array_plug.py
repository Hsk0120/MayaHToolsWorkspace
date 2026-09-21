"""multi (array) attribute plug wrapper."""

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

    def __getitem__(self, index):
        """論理インデックスの要素プラグを取得する。

        Args:
            index (int): 論理インデックス。

        Returns:
            Plug: 対応する要素プラグ。
        """
        return self.element(index)
