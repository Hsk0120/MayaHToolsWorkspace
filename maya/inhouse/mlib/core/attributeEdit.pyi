# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""動的アトリビュートをシーン変更前に組み立て、OpenMayaで追加する。"""

import maya.api.OpenMaya as om2
from .nodeEdit import require_editable
from typing import Any, Sequence
from mlib.nodes.node import Node
import re

_NUMERIC_TYPES: dict
_DATA_TYPES: dict
_PROPERTIES: dict
_DEFINITION_FLAGS: Any

def _build(flags: dict, children: list[om2.MObject] | None = ...) -> om2.MObject:
    """未登録のアトリビュート定義を作る。失敗してもシーンは変えない。

    Args:
        flags (dict): 正規化済みのaddAttrフラグ。
        children (list[MObject] | None): 先に構築した子定義。

    Returns:
        MObject: 新しいアトリビュート定義。

    Raises:
        ValueError: longName・shortNameのどちらも無い場合。
        NotImplementedError: fastで扱えないフラグ・型の場合。
    """
    ...

def _attach(node: Node, attribute: om2.MObject) -> None:
    """構築済み定義をノードへ一回で追加する。

    Args:
        node (Node): 追加先。
        attribute (MObject): シーン未登録のアトリビュート定義。

    Returns:
        None: 値を返さない。

    Raises:
        RuntimeError: ノードがロック・参照されている、または同名のアトリビュートがある場合。
    """
    ...

def extra_children(name: str, flags: dict, numeric: re.Match | None, count: int, *, deferred: object, child_names: Sequence[str] | None, child_short_names: Sequence[str] | None, child_suffixes: Sequence[str] | None, sub_type: str | None) -> list[tuple[str, str, dict]]:
    """自動生成する子の名前・成分数を、親追加より前に検証する。

    Args:
        name (str): 親の長名。
        flags (dict): 親の正規化済みフラグ。変更しない。
        numeric (Match | None): 数値のコンパウンドアトリビュートの一致結果。
        count (int): 子数。
        deferred (object): 子へ配る既定値。
        child_names (Sequence[str] | None): 子の長名。
        child_short_names (Sequence[str] | None): 子の短名。
        child_suffixes (Sequence[str] | None): 自動生成名の接尾辞。
        sub_type (str | None): 子の共通型。

    Returns:
        list[tuple[str, str, dict]]: 長名・型・公開addAttrへ渡すフラグ。

    Raises:
        ValueError: 子の名前・既定値・範囲の個数が子数と異なる場合。
    """
    ...

def validate_extra_attribute(node: Node, name: str, flags: dict, count: int, deferred: object, children: list[tuple[str, str, dict]], *, validate_defaults: bool = ...) -> None:
    """名前の衝突と検証可能なtyped既定値を、シーン変更前に拒否する。

    Args:
        node (Node): 追加先。
        name (str): 親の長名。
        flags (dict): 親の正規化済みフラグ。
        count (int): 子数。
        deferred (object): 作成後に設定する既定値。
        children (list[tuple[str, str, dict]]): 検証済みの子の作成入力。
        validate_defaults (bool): 通常経路の既定値も登録前に検証するか。
            fast経路では未登録の親子定義の構築時に検証するためFalse。

    Returns:
        None: 値を返さない。

    Raises:
        TypeError: マルチアトリビュートへ既定値を直接設定しようとした場合。
        ValueError: 名前が空文字列または文字列以外の場合。
        RuntimeError: 同名のアトリビュートがある、または書込み禁止の定義へ既定値を渡した場合。
    """
    ...

def create_extra_attribute(node: Node, name: str, flags: dict, numeric: re.Match | None, count: int, *, deferred: object, child_names: Sequence[str] | None, child_short_names: Sequence[str] | None, child_suffixes: Sequence[str] | None, sub_type: str | None) -> tuple | None:
    """Node.addAttrの親子定義を登録前に全て作る。

    Args:
        node (Node): 追加先。
        name (str): 親名。
        flags (dict): 親フラグ。
        numeric (Match | None): 数値のコンパウンドアトリビュートの一致結果。
        count (int): 子数。
        deferred (object): 子の既定値。
        child_names (Sequence[str] | None): 子の長名。
        child_short_names (Sequence[str] | None): 子の短名。
        child_suffixes (Sequence[str] | None): 子名の接尾辞。
        sub_type (str | None): 子の型。

    Returns:
        tuple | None: 型付き既定値の検証済み書込み計画。データownerを含む。
    """
    ...
