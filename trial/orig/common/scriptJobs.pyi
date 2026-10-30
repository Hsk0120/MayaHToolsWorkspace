# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""複数のscriptJobを所有者単位で管理する。"""

from contextlib import contextmanager
from .. import logger
from .scriptJob import ScriptJob
from typing import Any, Hashable, Iterator
from mlib._stubtypes import GeneratorContextManager



class ScriptJobs:
    """複数のscriptJobを所有者単位で管理する。GC時には自動解除しない。"""
    def __init__(self) -> None:
        """登録を伴わない空の監視グループを作る。"""
        ...
    def add(self, key: Hashable, **options: object) -> ScriptJob:
        """キーに対応する監視を追加する。生存中の同じキーは再登録しない。

        Args:
            key (Hashable): 所有者内で一意な識別子。
            **options (object): ScriptJobへ渡す登録オプション。

        Returns:
            ScriptJob: 既存または新規の監視。既存の場合optionsは適用しない。

        Raises:
            RuntimeError: Mayaが監視を登録できない場合。
        """
        ...
    def exists(self) -> bool:
        """所有する監視が空でなく、すべて生存しているか照会する。

        Returns:
            bool: 全監視が生存している場合はTrue。
        """
        ...
    def stop(self):
        """所有する全監視の解除を試み、成功分だけを保持表から除く。

        通常の解除例外は警告して残りも処理し、失敗した監視は後からstop()で再試行できる。
        他の所有者の監視は解除しない。

        Raises:
            RuntimeError: 解除失敗が一つ以上ある場合。最初の原因例外を__cause__に保持する。
        """
        ...
    def temporary(self) -> GeneratorContextManager[ScriptJobs]:
        """終了時に、このグループが持つ監視を解除する。

        開始前からの監視も対象で、UI・シーン自体の寿命は管理しない。
        失敗した監視は保持し、stop()で再試行できる。本文が失敗した場合は解除時の通常例外で置き換えない。

        Yields:
            ScriptJobs: 自身。

        Raises:
            RuntimeError: 同一インスタンスで入れ子にした、または正常終了時に解除が失敗した場合。
        """
        ...
