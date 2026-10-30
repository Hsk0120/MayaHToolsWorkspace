# tools/generate_mlib_stubs.py が生成した、スタブだけで使う補助の型。実行時には存在しない。
import contextlib
from typing import Any, Callable, Generic, TypeVar

_F = TypeVar("_F", bound=Callable[..., Any])
_T = TypeVar("_T")


class ContextDecorator(contextlib.ContextDecorator, contextlib.AbstractContextManager[Any]):
    """with とデコレーターの両方に使えるコンテキスト。"""

    def __call__(self, func: _F) -> _F: ...


class GeneratorContextManager(contextlib.ContextDecorator, contextlib.AbstractContextManager[_T], Generic[_T]):
    """contextlib.contextmanager が返す、with とデコレーターの両方に使えるコンテキスト。"""

    def __enter__(self) -> _T: ...

    def __call__(self, func: _F) -> _F: ...
