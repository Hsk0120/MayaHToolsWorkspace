"""ドリブンキー関係の検索と保持順コレクション。"""

from .._core.collection import BulkCollection, bulk_api
from .drivenKey import DrivenKey, _plug, _curves, _sources, _contains_plug


@bulk_api(
    DrivenKey,
    reads=(
        'driver_plug',
        'driven_plug',
        'curves',
        'exists',
    ),
    writes=(
        'set_key',
    ),
)
class DrivenKeys(BulkCollection):
    """DrivenKeyの保持順コレクション。同名メソッドを一括実行できる。"""

    def __init__(self, items=()):
        """Iterable[DrivenKey]を保持する。不正要素はTypeError。"""
        self._items = list(items)
        if any(not isinstance(item, DrivenKey) for item in self._items):
            raise TypeError("Expected DrivenKey objects")

    def __iter__(self):
        """Iterator[DrivenKey]: 保持順の要素。"""
        return iter(self._items)

    @classmethod
    def find(cls, driven):
        """駆動先に接続された関係を取得する。シーンは変更しない。

        Args:
            driven (Plug | om2.MPlug | str): 検索する駆動先アトリビュート。文字列は ``"node.attribute"`` 形式。
        Returns:
            DrivenKeys: 対応するドライバーごとの関係。対象外の構成は含めない
                (数値スカラーでないドライバー。``choice.output`` のような値によって型が
                変わる generic アトリビュートなど)。同じドライバー(プラグ自体で照合する)は1件にまとめる。
        Raises:
            ValueError: driven が非スカラー・非数値の場合。
            TypeError: driven が Plug・MPlug・アトリビュート名のいずれでもない場合。
            RuntimeError: driven のアトリビュートが存在しない場合。
        """
        target = _plug(driven)
        items, seen = [], []
        for curve in _curves(target):
            for source in _sources(curve.full_name() + ".input"):
                try:
                    driver = _plug(source)
                except ValueError:
                    continue  # 数値スカラーでないドライバーは DrivenKey の対象外。
                if not _contains_plug(seen, driver.mplug()):
                    seen.append(driver.mplug())
                    items.append(DrivenKey(driver, target))
        return cls(items)
