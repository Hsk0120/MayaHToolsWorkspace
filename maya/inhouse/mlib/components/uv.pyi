# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Mesh の現在の UV セットを参照する UV 型。"""

import numbers
import maya.api.OpenMaya as om2
import maya.cmds as cmds
from ..decorator import _edit_context, _require_bool
from ..util import _finite, _finite_vector
from .component import Component, Components
from typing import Any, Iterable, Iterator
from mlib.components.vertex import Vertex
from mlib.nodes.mesh import Mesh
from typing import overload



class UV(Component):
    """Mesh参照とUV番号を保持し、現在のUVセットのU/V座標を照会・編集する。

    UVセット名は固定して保持しない。切替後は同じ番号で切替先のセットを参照する。
    U/Vは無次元で、0〜1に制限しない。書込みは通常 ``cmds.polyEditUV`` で1回のUndoにまとめ、
    ``fast=True`` は ``MFnMesh.setUV`` / ``setUVs`` で書き込んでUndoに記録しない。
    """
    shape_type: str
    component_type: str
    count_attribute: str
    def getPosition(self) -> tuple[float, float]:
        """現在のUVセットから、保持番号のU/V座標を取得する。

        Returns:
            tuple[float, float]: 新しい無次元の(U, V)値。UI距離単位やobject/ワールド空間とは無関係。

        Raises:
            IndexError: 保持番号が現在のUVセットの範囲外の場合。
            RuntimeError: Meshまたは現在のUVセットを参照できない場合。
        """
        ...
    def setPosition(self, value: Iterable[float], *, fast: bool = ...) -> UV:
        """現在のUVセットの保持番号へ、絶対U/V座標を設定する。移動量ではない。

        通常は ``cmds.polyEditUV(relative=False)`` で書き込み、1回のUndoにまとめる。
        ``fast=True`` は ``MFnMesh.setUV`` で書き込み、Undoに記録しない(1点で約5倍速い)。

        Args:
            value (Iterable[float]): 有限なU/Vの2成分。無次元で0〜1に限定しない。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            UV: 自身。UVセットや割当ては作成しない。

        Raises:
            TypeError: fastがbool以外、または座標の型が不正な場合。
            ValueError: 座標が2成分の有限値でない場合。
            IndexError: 番号が現在のUVセットの範囲外の場合。
            RuntimeError: Meshが無効・ロックされている、またはMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、inMeshへの入力(コンストラクションヒストリ)がある場合。
        """
        ...
    def getU(self) -> float:
        """U成分の現在値を取得する。

        Returns:
            float: 座標値。
        """
        ...
    def setU(self, value: float, *, fast: bool = ...) -> UV:
        """U成分だけを設定し、Vは現在値を保つ。

        Args:
            value (float): 有限なU。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            UV: 自身。

        Raises:
            TypeError: fastがbool以外、またはvalueが数値でない場合。
            ValueError: valueが有限でない場合。
            IndexError: 番号が現在のUVセットの範囲外の場合。
            RuntimeError: Meshが無効・ロックされている、またはMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、inMeshへの入力がある場合。
        """
        ...
    def getV(self) -> float:
        """V成分の現在値を取得する。

        Returns:
            float: 座標値。
        """
        ...
    def setV(self, value: float, *, fast: bool = ...) -> UV:
        """V成分だけを設定し、Uは現在値を保つ。

        Args:
            value (float): 有限なV。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            UV: 自身。

        Raises:
            TypeError: fastがbool以外、またはvalueが数値でない場合。
            ValueError: valueが有限でない場合。
            IndexError: 番号が現在のUVセットの範囲外の場合。
            RuntimeError: Meshが無効・ロックされている、またはMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、inMeshへの入力がある場合。
        """
        ...
    def getVertex(self) -> Vertex | None:
        """このUVが割り当てられた頂点を取得する(現在のUVセット)。

        Returns:
            Vertex | None: 頂点。どのフェースにも割り当てられていないUVはNone。

        Raises:
            IndexError: 番号が現在のUVセットの範囲外の場合。
            RuntimeError: Meshまたは現在のUVセットを参照できない場合。
        """
        ...
    def _set_coordinate(self, axis: int, value: float, fast: bool, method: str, chunk: str) -> UV:
        """1成分だけを書き換えたU/Vを書き込む。

        Args:
            axis (int): 成分番号(0=U、1=V)。
            value (float): 設定する値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
            method (str): 例外の文言に使う公開メソッド名。
            chunk (str): Undoチャンク名。

        Returns:
            UV: 自身。
        """
        ...
_UV_GET_POSITION: Any


class UVs(Components):
    """同一MeshのUV番号列を保持し、現在のUVセットの座標を保持順に照会・一括編集する。

    セット名や座標値は保持せず、セット切替後は切替先の同じ番号を使う。
    setPositionは同じU/Vを全要素へ、setPositionsは保持番号ごとに異なる行を設定する。
    書込みは入力をすべて検証してから行う。通常は ``cmds.polyEditUV`` をUVごとに呼んで1回のUndoに
    まとめ(Mayaが途中で拒否した場合は先に書いたUVを戻す)、``fast=True`` は ``MFnMesh.setUVs`` で
    全UVを1回で書き込んでUndoに記録しない。
    """
    def __iter__(self) -> Iterator[UV]: ...
    @overload
    def __getitem__(self, index: int) -> UV: ...
    @overload
    def __getitem__(self, index: slice) -> UVs: ...
    component_class: Any
    def getU(self) -> list[float]:
        """U成分の現在値を取得する。

        Returns:
            list[float]: 保持順の座標値。
        """
        ...
    def setU(self, value: float | Iterable[float], *, fast: bool = ...) -> UVs:
        """U成分だけを設定し、Vは現在値を保つ。

        Args:
            value (float | Iterable[float]): 全要素に共通の値、または保持順の値列。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            UVs: 自身。

        Raises:
            TypeError: fastがbool以外、または値の型が不正な場合。
            ValueError: 値が有限でない、または値列の件数が保持数と違う場合。
            IndexError: 保持番号が現在のUVセットの範囲外の場合。
            RuntimeError: Meshが無効・ロックされている、またはMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、inMeshへの入力がある場合。
        """
        ...
    def getV(self) -> list[float]:
        """V成分の現在値を取得する。

        Returns:
            list[float]: 保持順の座標値。
        """
        ...
    def setV(self, value: float | Iterable[float], *, fast: bool = ...) -> UVs:
        """V成分だけを設定し、Uは現在値を保つ。

        Args:
            value (float | Iterable[float]): 全要素に共通の値、または保持順の値列。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            UVs: 自身。

        Raises:
            TypeError: fastがbool以外、または値の型が不正な場合。
            ValueError: 値が有限でない、または値列の件数が保持数と違う場合。
            IndexError: 保持番号が現在のUVセットの範囲外の場合。
            RuntimeError: Meshが無効・ロックされている、またはMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、inMeshへの入力がある場合。
        """
        ...
    def getPosition(self) -> list[tuple[float, float]]:
        """現在のUVセットのU/V座標を、保持番号の順に取得する。

        標準実装は同じMFnMeshと現在UVセット名を使って各番号を問い合わせる。
        単数参照や反復が拡張されている場合は、各要素のgetPositionへ委譲する。

        Returns:
            list[tuple[float, float]]: 新しい無次元のU/V値リスト。座標への書換え可能な参照ではない。
                標準実装の空集合は、Shapeを再照会せず空リストを返す。

        Raises:
            IndexError: 保持番号が現在のUVセットの範囲外の場合。
            RuntimeError: Meshまたは現在のUVセットを参照できない場合。
        """
        ...
    def setPosition(self, value: Iterable[float], *, fast: bool = ...) -> UVs:
        """保持する全UVを、現在のUVセットで同じ絶対U/V座標へ集める。

        要素ごとに違う座標は :meth:`setPositions` を使う。

        Args:
            value (Iterable[float]): 全要素に共通の有限なU/V。無次元。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            UVs: 自身。空集合は入力だけを検証して何もしない。

        Raises:
            TypeError: fastがbool以外、または座標の型が不正な場合。
            ValueError: 座標が2成分の有限値でない場合。
            IndexError: 保持番号が現在のUVセットの範囲外の場合。
            RuntimeError: Meshが無効・ロックされている、またはMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、inMeshへの入力がある場合。
        """
        ...
    def setPositions(self, values: Iterable[Iterable[float]], *, fast: bool = ...) -> UVs:
        """現在のUVセットへ、保持番号の順に絶対(U, V)を設定する。

        件数・有限値・現在の番号範囲を先にすべて検証し、問題があればシーンを変更しない。
        通常は ``cmds.polyEditUV`` をUVごとに呼ぶ(目安は1UVあたり約1ms)。``fast=True`` は
        ``MFnMesh.setUVs`` で全UVを1回で書き込む。

        Args:
            values (Iterable[Iterable[float]]): 保持番号と同じ件数の有限な(U, V)。無次元。
                :meth:`getPosition` の結果をそのまま受け付ける。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            UVs: 自身。空集合と空列はShapeを再照会せず何もしない。

        Raises:
            TypeError: fastがbool以外、または座標の型が不正な場合。
            ValueError: 件数が保持数と違う、または座標が2成分の有限値でない場合。
            IndexError: 保持番号が現在のUVセットの範囲外の場合。
            RuntimeError: Meshが無効・ロックされている、またはMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、inMeshへの入力がある場合。

        Note:
            UVセット・割当ての作成は行わない。
        """
        ...
    def _set_coordinates(self, axis: int, value: float | Iterable[float], fast: bool, method: str, chunk: str) -> UVs:
        """保持順の1成分だけを書き換えたU/Vを書き込む。

        Args:
            axis (int): 成分番号(0=U、1=V)。
            value (float | Iterable[float]): 共通の値または保持順の値列。
            fast (bool): TrueはUndoなしのOpenMaya更新。
            method (str): 例外の文言に使う公開メソッド名。
            chunk (str): Undoチャンク名。

        Returns:
            UVs: 自身。
        """
        ...
    def _write(self, rows: list[tuple[float, float]], fast: bool, method: str, chunk: str) -> UVs:
        """検証済みのU/V行を、番号範囲を確かめてから書き込む。

        Args:
            rows (list[tuple[float, float]]): 保持順のU/V。
            fast (bool): TrueはUndoなしのOpenMaya更新。
            method (str): 例外の文言に使う公開メソッド名。
            chunk (str): Undoチャンク名。

        Returns:
            UVs: 自身。
        """
        ...
    def getVertex(self) -> list[Vertex | None]:
        """各要素の :meth:`~mlib.components.uv.UV.getVertex` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def getFullName(self) -> list[str]:
        """各要素の :meth:`~mlib.components.component.Component.getFullName` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def asString(self) -> list[str]:
        """各要素の :meth:`~mlib.core.object.Object.asString` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...

def _uv_value(value: Iterable[float]) -> tuple[float, float]:
    """1つのU/Vを検証し、floatのtupleへ変換する。

    Args:
        value (Iterable[float]): U/Vの2成分。

    Returns:
        tuple[float, float]: 変換済みのU/V。

    Raises:
        TypeError: 反復できない、文字列、または成分が数値でない場合。
        ValueError: 2成分でない、または有限でない場合。
    """
    ...

def _axis_values(value: float | Iterable[float], count: int) -> list[float]:
    """1成分の値を、共通のスカラーまたは保持順の値列として検証する。

    Args:
        value (float | Iterable[float]): 共通の値、または件数countの値列。
        count (int): 保持している要素数。

    Returns:
        list[float]: 件数countの有限な値。

    Raises:
        TypeError: 数値・数値の列でない場合(文字列を含む)。
        ValueError: 有限でない、または値列の件数がcountと違う場合。
    """
    ...

def _write_uvs(shape: Mesh, indices: list[int], rows: list[tuple[float, float]], fast: bool, method: str, chunk: str):
    """検証済みのU/Vを、現在のUVセットへ書き込む。

    Args:
        shape (Mesh): 対象のMesh。番号は検証済み。
        indices (list[int]): UV番号。
        rows (list[tuple[float, float]]): 番号と同じ件数のU/V。
        fast (bool): TrueはUndoなしのOpenMaya更新。
        method (str): 例外の文言に使う公開メソッド名。
        chunk (str): 通常経路のUndoチャンク名。

    Raises:
        RuntimeError: Meshがロックされている、またはMayaが書込みを拒否した場合。
        NotImplementedError: fastで、inMeshへの入力がある場合。
    """
    ...

def _write_uvs_fast(mesh_fn: om2.MFnMesh, uv_set: str, indices: list[int], rows: list[tuple[float, float]]):
    """U/VをOpenMayaで書き込む。1点は ``setUV``、複数は全UVを ``setUVs`` で1回に書く。

    Args:
        mesh_fn (om2.MFnMesh): 対象のMeshの関数セット。
        uv_set (str): 書き込むUVセット名。
        indices (list[int]): UV番号。重複は後の値を優先する。
        rows (list[tuple[float, float]]): 番号と同じ件数のU/V。
    """
    ...
