# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Python探索パス直下のmlib_*拡張を検出する。独自Mayaプラグインはロードしない。"""

import ast
import importlib
import importlib.machinery
import os
import pkgutil
import re
import sys
import tokenize
from collections.abc import Mapping
from pathlib import Path
from .. import logger
from typing import Any, Iterable
from mlib.core.registry import NodeRegistry
from types import ModuleType

__all__ = ['status', 'getDiagnostics']
_states: dict
_loading: bool
_diagnosing: bool
_package_name: Any
_extension_pattern: Any
_attempted: Any

def status() -> dict:
    """最後の初期化で得た拡張名ごとの状態と理由をコピーして返す。

    現在の依存可用性は再照会しない。診断だけを更新する場合はgetDiagnosticsを使う。

    Returns:
        dict: 拡張名ごとの状態と理由をコピーして返す。
    """
    ...

def getDiagnostics() -> dict[str, dict]:
    """初期化時の記録と、読込み済み宣言の現在の可用性を分けて取得する。

    status()は初期化記録だけを返す。この関数はis_available()を再照会するが、拡張の新規import・
    型登録・reload・Mayaプラグインのロードは行わない。is_available側は依存を遅延importできるが、
    シーン/UIを変更しないことが宣言の契約となる。

    Returns:
        dict[str, dict]: initializationは初期化記録のコピー(未記録ならNone)、availableはbool。
            宣言未読込・初期化中・宣言不正・再入・照会失敗ではavailable=Noneで、reasonへ理由を入れる。
            初期化記録と登録表は変更しない。
    """
    ...

def _prepare_reload():
    """本体の再読み込み前に、宣言済み・読み込み失敗の拡張をまとめて解除する。

    外部SDKやMayaプラグインは対象外。保持済みのPython参照は利用側で取得し直す。
    初期化途中の再入では、モジュールを一つも削除せず拒否する。
    """
    ...

def _is_available(package: ModuleType) -> bool:
    """宣言の可用性を照会し、初期化と診断で同じ型検証を使う。

    Args:
        package (ModuleType): 宣言の読み込みを完了した拡張パッケージ。

    Returns:
        bool: 拡張が現在利用可能か。

    Raises:
        TypeError: is_availableがcallableでない、またはboolを返さない場合。
    """
    ...

def _require_dependencies(name: str, locations: Iterable[str]) -> None:
    """拡張のPythonソースにある他拡張へのimportを登録前に拒否する。

    Args:
        name (str): 検査する拡張名。
        locations (Iterable[str]): パッケージの親フォルダー。

    Returns:
        None: 値を返さない。

    Raises:
        ValueError: 他のmlib_*へのimportがある場合。

    Note:
        動的importまで実行して解析しない。拡張作者は動的importでも同じ規則に従う。
    """
    ...

def _find_candidates() -> dict[str, set[str]]:
    """探索パスの重複を除き、拡張名ごとの実配置を収集する。

    Returns:
        dict[str, set[str]]: 拡張名と正規化した配置先。importは行わない。
    """
    ...

def _may_contain_candidate(path: str) -> bool:
    """探索パスの直下に拡張名と一致する項目があり得るかを、パッケージ判定の前に調べる。

    pkgutil.iter_modulesは通常のフォルダーに対して全サブフォルダーの中身を一覧するため、
    Mayaの長い探索パスでは起動が遅くなる。通常のフォルダー(FileFinder)でパッケージとして
    返る名前はフォルダー名そのものなので、直下に名前が一致する項目が無ければ結果は空になる。
    zip等の他のimporterは判定せず、従来どおりiter_modulesへ任せる。

    Args:
        path (str): sys.pathの1項目。

    Returns:
        bool: iter_modulesで拡張の候補を探す必要があればTrue。
    """
    ...

def _load_candidate(name: str, locations: set[str]) -> dict | None:
    """拡張の軽量な宣言を読み、対象外・利用不可ならその状態を返す。

    Args:
        name (str): 検出した拡張名。
        locations (set[str]): 拡張が存在する親フォルダー。

    Returns:
        dict | None: 読み飛ばす場合の状態。利用可能な拡張ならNone。

    Raises:
        TypeError: 可用性判定がboolを返さない場合。
        ValueError: 同じ名前の拡張が複数箇所にある場合。
        RuntimeError: 拡張の初期化中に再入した場合。
    """
    ...

def _validated_entries(name: str, bases: Iterable[tuple[str, type]]) -> list[tuple[NodeRegistry, dict[str, type]]]:
    """全種類の明示宣言を検証し、まだ登録せずに対応表を集める。

    Args:
        name (str): 利用可能な拡張名。
        bases (Iterable[tuple[str, type]]): サブパッケージ名と必須の基底型。

    Returns:
        list[tuple[NodeRegistry, dict[str, type]]]: 登録表と検証済みの型対応。

    Raises:
        TypeError: 宣言・基底型・他拡張からの継承が不正な場合。
        ValueError: 型名が不正、または既存登録と衝突する場合。
    """
    ...

def _apply_entries(entries: list[tuple[NodeRegistry, dict[str, type]]]) -> None:
    """検証済みの全登録表を更新し、途中の障害では全表を元に戻す。

    Args:
        entries (list[tuple[NodeRegistry, dict[str, type]]]): 適用する型対応。

    Returns:
        None: 値を返さない。

    Raises:
        Exception: 復元後、登録中の例外をそのまま再送出する。
    """
    ...

def _initialize():
    """標準登録完了後に拡張を検出し、拡張単位で検証して登録する。"""
    ...
