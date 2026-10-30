# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""真偽値アトリビュートと値の反転操作を提供する。"""

from .plug import Plug



class BoolPlug(Plug):
    """bool アトリビュート用の Plug。"""
    def toggle(self) -> Plug:
        """真偽値を反転する。

        Returns:
            Plug: 自身。
        """
        ...
