# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""ヘッダー付きのJSONファイルを書き出し・読み込み、形式名と版を検査する。

ファイルは ``{"header": {...}, "data": {...}}`` の形で、UTF-8・整形(字下げ2)で書く。
ヘッダーは形式名・版・書き出したmlibとMayaの版・単位(長さcm・角度は度・時間は保存時の
UI時間単位のフレームと、そのfps)を持つ。データの数学型は :mod:`mlib.json.codec` で変換する。
"""

import json
import os
import tempfile
from pathlib import Path
import maya.api.OpenMaya as om2
import maya.cmds as cmds
from .codec import decode, encode
import pathlib

_LINEAR_UNIT: str
_ANGLE_UNIT: str
_TIME_UNIT: str
_TIMINGS: tuple


class Header:
    """JSONファイルのヘッダー(形式名・版・書き出した環境・単位)を保持する。

    :func:`load` が返し、時間の換算(:meth:`convertTime`)に使う。書き出し時は :func:`dump` が
    現在のシーンから作るので、直接作る必要はない。
    """
    def __init__(self, format: str, version: int, mlib: str | None = ..., maya: str | None = ..., fps: float | None = ...) -> None:
        """ヘッダーの値を保持する。

        Args:
            format (str): 形式名(``"mlib.pose"`` 等)。
            version (int): 形式の版。
            mlib (str | None): 書き出したmlibの版。
            maya (str | None): 書き出したMayaの版。
            fps (float | None): 書き出したシーンのfps。Noneは現在のシーンのfps。

        Raises:
            TypeError: formatが文字列でない、versionがint以外(boolを含む)、またはfpsが数値・None以外の場合。
            ValueError: formatが空、versionが1未満、またはfpsが正でない場合。
        """
        ...
    def __repr__(self) -> str:
        """形式名・版・fpsを含む表記を返す。

        Returns:
            str: ``Header('mlib.pose', 1, fps=30.0)`` の形式。
        """
        ...
    @classmethod
    def fromData(cls, data: dict) -> Header:
        """ファイルのヘッダーの辞書から作る。

        Args:
            data (dict): :meth:`toData` の形の辞書。

        Returns:
            Header: 新しいヘッダー。

        Raises:
            ValueError: 必要なキーが無い、または単位が対応外の場合。
        """
        ...
    @property
    def format(self) -> str:
        """形式名を返す。

        Returns:
            str: ``"mlib.pose"`` 等。
        """
        ...
    @property
    def version(self) -> int:
        """形式の版を返す。

        Returns:
            int: 版。
        """
        ...
    @property
    def mlib(self) -> str | None:
        """書き出したmlibの版を返す。

        Returns:
            str | None: 版。不明ならNone。
        """
        ...
    @property
    def maya(self) -> str | None:
        """書き出したMayaの版を返す。

        Returns:
            str | None: 版。不明ならNone。
        """
        ...
    @property
    def fps(self) -> float:
        """書き出したシーンのfpsを返す。

        Returns:
            float: 1秒あたりのフレーム数。
        """
        ...
    def convertTime(self, frame: float, timing: str = ...) -> float:
        """保存時のフレームを、現在のシーンのフレームへ換算する。

        ``timing="frame"`` はフレーム番号をそのまま返す(何コマ目かを保つ)。``"second"`` は
        保存時のfpsで秒にしてから、現在のfpsのフレームへ直す(実際の時間を保つ)。
        fpsが同じならどちらも同じ値になる。

        Args:
            frame (float): 保存時のフレーム。
            timing (str): ``"frame"`` (既定)または ``"second"``。

        Returns:
            float: 現在のシーンのフレーム。

        Raises:
            ValueError: timingが ``"frame"``・``"second"`` 以外の場合。
        """
        ...
    def toData(self) -> dict:
        """ファイルに書くヘッダーの辞書を返す。

        Returns:
            dict: ``format``・``version``・``mlib``・``maya``・``units`` を持つ新しい辞書。
        """
        ...

def currentFps() -> float:
    """現在のシーンのUI時間単位のfpsを返す。

    Returns:
        float: 1秒あたりのフレーム数。
    """
    ...

def dump(data: dict, path: str | os.PathLike, format: str, version: int) -> pathlib.Path:
    """データにヘッダーを付けて、JSONファイルへ書き出す。

    データは :func:`mlib.json.codec.encode` で変換してから書く。同じフォルダの一時ファイルへ
    書いてから置き換えるので、途中で失敗しても既存のファイルは壊れない。フォルダは作らない。

    Args:
        data (dict): 書き出すデータ。数学型を含んでよい。
        path (str | os.PathLike): 書き出し先。
        format (str): 形式名(``"mlib.pose"`` 等)。
        version (int): 形式の版。

    Returns:
        pathlib.Path: 書き出したファイルの絶対パス。

    Raises:
        TypeError: dataが辞書でない、またはJSONで書けない値を含む場合。
        ValueError: 形式名・版が不正、またはNaN・無限大を含む場合。
        OSError: 書き出しに失敗した場合。
    """
    ...

def load(path: str | os.PathLike, format: str, version: int) -> tuple[Header, dict]:
    """JSONファイルを読み込み、形式名と版を検査してヘッダーとデータを返す。

    データは :func:`mlib.json.codec.decode` で数学型へ戻す。版の変換は行わない。

    Args:
        path (str | os.PathLike): 読み込むファイル。
        format (str): 期待する形式名。
        version (int): 期待する版。

    Returns:
        tuple[Header, dict]: ヘッダーとデータ。

    Raises:
        ValueError: JSONとして読めない、形式が違う、形式名・版が期待と違う、または単位が対応外の場合。
        OSError: 読み込みに失敗した場合。
    """
    ...

def _require_timing(timing: str):
    """時間の扱いの指定を検証する。

    Args:
        timing (str): ``"frame"`` または ``"second"``。

    Raises:
        ValueError: それ以外の場合。
    """
    ...
