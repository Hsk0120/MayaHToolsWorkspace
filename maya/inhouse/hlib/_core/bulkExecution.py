"""複数形の結果収集方針を決める内部処理。"""

import inspect


# 基底Nodes.callEachや利用側の同名メソッドにも従来どおり適用する。
_CALCULATING_SETTERS = frozenset((
    "setTranslate", "setRotate", "setQuaternion", "setScale", "setShearing",
    "setMatrix", "setTransformation",
))


def calculation_results(method, functions, args, kwargs):
    """get指定で計算値を返すsetterについて結果列が必要か判定する。

    Args:
        method (str): 一括実行するメソッド名。
        functions (Sequence[callable]): 実際の呼出し先。
        args (Sequence[tuple]): 要素別の位置引数。
        kwargs (Sequence[dict]): 要素別の正規化済みキーワード引数。
    Returns:
        bool: 少なくとも一つの対象がget指定で計算値を返す場合True。
    """
    if method not in _CALCULATING_SETTERS:
        return False
    return any(inspect.signature(fn).bind(*row, **flags).arguments.get("get", False)
               for fn, row, flags in zip(functions, args, kwargs))
