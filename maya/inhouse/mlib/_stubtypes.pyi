# tools/generate_mlib_stubs.py が生成した、スタブだけで使う補助の型。実行時には存在しない。
import contextlib
from typing import Any, Callable, TypeVar

_F = TypeVar("_F", bound=Callable[..., Any])


class ContextDecorator(contextlib.ContextDecorator, contextlib.AbstractContextManager[Any]):
    """with とデコレーターの両方に使えるコンテキスト。"""

    def __call__(self, func: _F) -> _F: ...
