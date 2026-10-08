"""明示したget省略入口へ正式getterの署名とフラグ情報を付与する。"""

import inspect


def _getter_alias(getter, *, static=False):
    """通常defの省略入口を補完し、処理本体や公開メソッドは生成しない。

    Args:
        getter (callable | classmethod | staticmethod): 委譲先の正式getter。
        static (bool): staticmethodをclassmethodから呼ぶ入口ならTrue。
            署名へclsだけを追加し、束縛後の引数を正式getterと一致させる。

    Returns:
        callable: 署名・フラグ・委譲先名だけを付与するデコレーター。

    Note:
        呼出し時の委譲先は入口のdefが解決する。元関数を固定して呼び出したり、
        Undoチャンク・フラグ正規化・キャッシュを追加したりしない。
    """
    function = getter.__func__ if isinstance(getter, (classmethod, staticmethod)) else getter
    signature = inspect.signature(function)
    if static:
        receiver = inspect.Parameter("cls", inspect.Parameter.POSITIONAL_OR_KEYWORD)
        signature = signature.replace(parameters=(receiver, *signature.parameters.values()))

    def decorate(alias):
        """正式getterの照会情報を、明示済みの省略defへコピーする。

        Args:
            alias (callable): 通常defで定義した省略入口。

        Returns:
            callable: 名前・本文・docstringを維持した同じ関数。
        """
        alias.__signature__ = signature
        alias.__annotations__ = dict(getattr(function, "__annotations__", {}))
        alias.__hlib_getter_name__ = function.__name__
        alias.__hlib_flag_aliases__ = dict(getattr(function, "__hlib_flag_aliases__", {}))
        alias.__hlib_maya_command__ = getattr(function, "__hlib_maya_command__", None)
        return alias

    return decorate
