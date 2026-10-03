"""コマンド固有の短縮フラグを、実行前に長名へ統一する。"""

import inspect
import re
from functools import lru_cache, wraps

import maya.cmds as cmds


@lru_cache(maxsize=None)
def _maya_aliases(command):
    """実行中のMayaが公開するフラグ一覧を取得する。初回呼び出し時のみ照会。"""
    help_text = cmds.help(command)
    aliases = dict(re.findall(r"^\s+-(\w+)\s+-(\w+)\b", help_text, re.MULTILINE))
    if not aliases:
        raise RuntimeError("Cannot read Maya flag definitions: " + command)
    # query/editはhelpのフラグ一覧に含まれないコマンドもある。
    # 対応モードかどうかの検査は元のMayaコマンドに任せる。
    aliases.update(q="query", e="edit")
    return aliases


def normalize_flags(function, kwargs):
    """関数の登録済み別名またはMayaコマンド名からフラグを正規化する。

    長名と短名の重複は拒否し、入力辞書は変更しない。

    Args:
        function (callable | str): 登録済み関数または Maya コマンド名。
        kwargs (dict): 正規化するキーワード引数。

    Returns:
        dict: 短名を長名に置き換えた新しい辞書。
    """
    if not kwargs:
        return {}
    aliases = getattr(function, "__hlib_flag_aliases__", {})
    command = function if isinstance(function, str) else getattr(function, "__hlib_maya_command__", None)
    if command:
        aliases = dict(_maya_aliases(command), **aliases)
    result = dict(kwargs)
    for short, long in aliases.items():
        if short not in result or short == long:
            continue
        if long in result:
            raise TypeError("Specify only one of {!r} and {!r}".format(long, short))
        result[long] = result.pop(short)
    return result


def flag_aliases(command=None, **aliases):
    """Mayaコマンド名または明示した短名=長名の対応を関数へ付与する。

    シグネチャとdocstringを保持する。別名の競合と位置引数との重複は
    関数本体（Undoチャンク等を含む）の実行前に検出する。

    Args:
        command (str | None): Maya コマンド名。
        **aliases: 短名をキー、長名を値とする対応。

    Returns:
        callable: フラグを正規化するデコレータ。
    """
    def decorate(function):
        signature = inspect.signature(function)

        @lru_cache(maxsize=128)
        def validate_shape(positional_count, names):
            """値に依存しない引数の形だけを検証し、成功した形を上限付きで保持する。

            値・ノード・Plugを保持しない。装飾ごとのキャッシュなのでreloadで
            新しい関数が作られたときに古いsignatureを再利用しない。
            """
            signature.bind(*([None] * positional_count), **dict.fromkeys(names))

        @wraps(function)
        def wrapped(*args, **kwargs):
            normalized = normalize_flags(wrapped, kwargs)
            validate_shape(len(args), tuple(normalized))
            return function(*args, **normalized)

        wrapped.__hlib_flag_aliases__ = dict(aliases)
        wrapped.__hlib_maya_command__ = command
        return wrapped
    return decorate
