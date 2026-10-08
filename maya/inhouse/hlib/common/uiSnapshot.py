"""同一Mayaセッションでのみ有効なUI状態のメモリ退避値。"""

from dataclasses import dataclass, field
from types import MappingProxyType


@dataclass(frozen=True)
class UiSnapshot:
    """変更不可の退避値。JSON化や別セッションへの持ち越しは対象外。

    scopeはwindow/workspaceControl。dataはその範囲の状態だけを
    保持する。エディタの内容・スクリプト・UIの再生成処理は含まない。
    """

    scope: str
    name: str
    data: object
    _targets: tuple = field(repr=False, compare=False)
    version: int = field(default=1, init=False)

    def __post_init__(self):
        """退避値と参照列をコピーし、利用側による書換えを防ぐ。"""
        object.__setattr__(self, "data", MappingProxyType(dict(self.data)))
        object.__setattr__(self, "_targets", tuple(self._targets))

    def __getitem__(self, name):
        """保持する状態値を取得する。Mayaへの照会は行わない。

        Args:
            name: 参照・作成・照会する対象の名前。
        """
        return self.data[name]

    def validate(self):
        """退避時のUIが全て生存するか確認する。同名の再生成UIは拒否する。"""
        if self.version != 1:
            raise ValueError("Unsupported UI snapshot version")
        for target in self._targets:
            target.getName()
