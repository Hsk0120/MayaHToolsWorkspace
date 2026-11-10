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

#: ヘッダーに書く単位。長さ・角度・時間の種類は固定で、fpsだけ保存時のシーンの値を書く。
_LINEAR_UNIT = "cm"
_ANGLE_UNIT = "deg"
_TIME_UNIT = "frame"
#: 読み込み時のfpsの扱い。"frame" はフレーム番号を保ち、"second" は秒を保つ。
_TIMINGS = ("frame", "second")


class Header:
    """JSONファイルのヘッダー(形式名・版・書き出した環境・単位)を保持する。

    :func:`load` が返し、時間の換算(:meth:`convertTime`)に使う。書き出し時は :func:`dump` が
    現在のシーンから作るので、直接作る必要はない。
    """

    def __init__(self, format, version, mlib=None, maya=None, fps=None):
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
        if not isinstance(format, str):
            raise TypeError("format must be a string")
        if not format:
            raise ValueError("format must not be empty")
        if isinstance(version, bool) or not isinstance(version, int):
            raise TypeError("version must be an int")
        if version < 1:
            raise ValueError("version must be 1 or greater")
        if fps is None:
            fps = currentFps()
        if isinstance(fps, bool) or not isinstance(fps, (int, float)):
            raise TypeError("fps must be a number")
        if not fps > 0:
            raise ValueError("fps must be positive")
        self._format = format
        self._version = version
        self._mlib = mlib
        self._maya = maya
        self._fps = float(fps)

    def __repr__(self):
        """形式名・版・fpsを含む表記を返す。

        Returns:
            str: ``Header('mlib.pose', 1, fps=30.0)`` の形式。
        """
        return f"Header({self._format!r}, {self._version}, fps={self._fps})"

    @classmethod
    def fromData(cls, data):
        """ファイルのヘッダーの辞書から作る。

        Args:
            data (dict): :meth:`toData` の形の辞書。

        Returns:
            Header: 新しいヘッダー。

        Raises:
            ValueError: 必要なキーが無い、または単位が対応外の場合。
        """
        if not isinstance(data, dict) or not isinstance(data.get("units"), dict):
            raise ValueError("JSON header must be an object with 'units'")
        units = data["units"]
        expected = {"linear": _LINEAR_UNIT, "angle": _ANGLE_UNIT, "time": _TIME_UNIT}
        for key, unit in expected.items():
            if units.get(key) != unit:
                raise ValueError(f"Unsupported {key} unit in JSON header: {units.get(key)!r} (expected {unit!r})")
        try:
            return cls(data["format"], data["version"], data.get("mlib"), data.get("maya"), units.get("fps"))
        except (KeyError, TypeError) as error:
            raise ValueError(f"Invalid JSON header: {error}") from error

    @property
    def format(self):
        """形式名を返す。

        Returns:
            str: ``"mlib.pose"`` 等。
        """
        return self._format

    @property
    def version(self):
        """形式の版を返す。

        Returns:
            int: 版。
        """
        return self._version

    @property
    def mlib(self):
        """書き出したmlibの版を返す。

        Returns:
            str | None: 版。不明ならNone。
        """
        return self._mlib

    @property
    def maya(self):
        """書き出したMayaの版を返す。

        Returns:
            str | None: 版。不明ならNone。
        """
        return self._maya

    @property
    def fps(self):
        """書き出したシーンのfpsを返す。

        Returns:
            float: 1秒あたりのフレーム数。
        """
        return self._fps

    def convertTime(self, frame, timing="frame"):
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
        _require_timing(timing)
        if timing == "frame":
            return frame
        return frame / self._fps * currentFps()

    def toData(self):
        """ファイルに書くヘッダーの辞書を返す。

        Returns:
            dict: ``format``・``version``・``mlib``・``maya``・``units`` を持つ新しい辞書。
        """
        return {"format": self._format, "version": self._version, "mlib": self._mlib, "maya": self._maya,
                "units": {"linear": _LINEAR_UNIT, "angle": _ANGLE_UNIT, "time": _TIME_UNIT, "fps": self._fps}}


def currentFps():
    """現在のシーンのUI時間単位のfpsを返す。

    Returns:
        float: 1秒あたりのフレーム数。
    """
    return 1.0 / om2.MTime(1, om2.MTime.uiUnit()).asUnits(om2.MTime.kSeconds)


def dump(data, path, format, version):
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
    if not isinstance(data, dict):
        raise TypeError("data must be a dict")
    # 循環参照の回避: mlib.__version__ はパッケージの初期化の最後に設定される。
    from .. import __version__
    header = Header(format, version, __version__, cmds.about(version=True))
    payload = {"header": header.toData(), "data": encode(data)}
    text = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)
    destination = Path(os.fspath(path)).resolve()
    descriptor, temporary = tempfile.mkstemp(prefix=".mlib-", suffix=".json", dir=str(destination.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text + "\n")
        os.replace(temporary, str(destination))
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)
    return destination


def load(path, format, version):
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
    with open(os.fspath(path), encoding="utf-8") as stream:
        try:
            payload = json.load(stream)
        except json.JSONDecodeError as error:
            raise ValueError(f"Cannot read {os.fspath(path)} as JSON: {error}") from error
    if not isinstance(payload, dict) or set(payload) != {"header", "data"} or not isinstance(payload["data"], dict):
        raise ValueError(f"{os.fspath(path)} is not an mlib JSON file (expected 'header' and 'data')")
    header = Header.fromData(payload["header"])
    if header.format != format:
        raise ValueError(f"{os.fspath(path)} has format {header.format!r}, expected {format!r}")
    if header.version != version:
        raise ValueError(f"{os.fspath(path)} has {format} version {header.version}, expected version {version}")
    return header, decode(payload["data"])


def _require_timing(timing):
    """時間の扱いの指定を検証する。

    Args:
        timing (str): ``"frame"`` または ``"second"``。

    Raises:
        ValueError: それ以外の場合。
    """
    if timing not in _TIMINGS:
        raise ValueError(f"timing must be 'frame' or 'second', got {timing!r}")
