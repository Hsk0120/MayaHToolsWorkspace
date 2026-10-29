# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""列挙値。getは整数値、setは整数値またはフィールド名、getEnumName/getEnumValueは名前と値を扱う。"""

from .plug import Plug



class EnumPlug(Plug):
    """列挙値。getは整数値、setは整数値またはフィールド名、getEnumName/getEnumValueは名前と値を扱う。

    ``set("head")`` のようにフィールド名を渡すと :meth:`getEnumValue` で値へ変換して書き込む
    (大文字・小文字を区別する完全一致。通常・fast・safeで同じ)。一致しない名前は有効な名前を並べた
    ValueError(``safe=True`` では失敗数1)。
    """
    def _set_value(self, value: int | str, *, uiUnits: bool = ..., fast: bool = ...) -> None:
        """フィールド名を整数値へ変換してから基底の書込みへ渡す。

        Args:
            value (int | str): enum値またはフィールド名。
            uiUnits (bool): 基底の書込みへ渡す単位指定。
            fast (bool): TrueならOpenMayaで直接更新する。

        Returns:
            None: 値を返さない。

        Raises:
            ValueError: フィールド名に一致するフィールドが無い場合。
        """
        ...
