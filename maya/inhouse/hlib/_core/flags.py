"""コマンド固有の短縮フラグを、実行前に長名へ統一する。"""

from functools import lru_cache, wraps
import inspect
import re

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
    """登録済み別名だけを変換し、長名との重複を拒否したコピーを返す。"""
    aliases = dict(getattr(function, "__hlib_flag_aliases__", {}))
    command = getattr(function, "__hlib_maya_command__", None)
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
    """
    def decorate(function):
        signature = inspect.signature(function)

        @wraps(function)
        def wrapped(*args, **kwargs):
            normalized = normalize_flags(wrapped, kwargs)
            signature.bind(*args, **normalized)
            return function(*args, **normalized)

        wrapped.__hlib_flag_aliases__ = dict(aliases)
        wrapped.__hlib_maya_command__ = command
        return wrapped
    return decorate
