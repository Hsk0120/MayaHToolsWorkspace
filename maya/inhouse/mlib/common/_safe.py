"""Plugのsafe指定を共通処理し、書込みに失敗した成分数を返す。"""

import inspect
from functools import wraps


def safe_edit(function):
    """safe=Trueで書込み失敗を数え、複合値は書ける子を更新する。

    Args:
        function (callable): valueとsafe引数を持つPlugのsetter。
    Returns:
        callable: 通常時は元の戻り値、safe時は失敗数を返す関数。
    """
    signature = inspect.signature(function)

    @wraps(function)
    def wrapped(self, *args, **kwargs):
        if len(args) <= 1 and not kwargs.get("safe", False):
            return function(self, *args, **kwargs)
        bound = signature.bind(self, *args, **kwargs)
        if not bound.arguments.get("safe", False):
            return function(self, *args, **kwargs)
        bound.arguments["safe"] = False
        # multi全体へのsetはsafeでも許可しない。
        if self.isArray():
            return function(*bound.args, **bound.kwargs)
        try:
            function(*bound.args, **bound.kwargs)
            return 0
        except (RuntimeError, TypeError, ValueError):
            if not self.isValid() or not self.mplug().isCompound:
                return 1
            try:
                values = bound.arguments["value"]
                if hasattr(self, "_set_components"):
                    values = self._set_components(values, bound.arguments.get("unit", "rad"))
                values = tuple(values)
                if len(values) != self.mplug().numChildren():
                    return 1
                return sum(getattr(self[i], function.__name__)(v, safe=True)
                           for i, v in enumerate(values))
            except (RuntimeError, TypeError, ValueError):
                return 1
    return wrapped
