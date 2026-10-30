# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""形状座標の照会と通常/fast更新。通常はcmds、fastは履歴なし形状へ直接書く。"""

from collections import namedtuple
import maya.api.OpenMaya as om2
import maya.cmds as cmds
from .fastWrite import require_writable
from typing import Any, Iterable, NamedTuple, Sequence
from mlib.nodes.mesh import Mesh
from mlib.nodes.nurbsCurve import NurbsCurve
from mlib.nodes.shape import Shape


class _Geometry(NamedTuple):
    path: Any
    fn: Any
    is_mesh: Any

def geometry(shape: Mesh | NurbsCurve, indices: Iterable[int], edit: bool = ...) -> _Geometry:
    """Shapeの保持DAGパスと関数セットを取得し、必要なら直接編集の前提を検査する。

    呼出し側がShape型と番号範囲を検証済みであることを前提とする。edit=Trueでは
    周期カーブ、inMesh/createへの入力、Shapeノードのロックを検査する。
    指定点のpnts/controlPointsとその子についても、上位を含むロック・入力接続と、各対象アトリビュートの書込み可否を調べる。
    indicesが空のUV更新では、点Plugごとの検査は行わない。

    Args:
        shape (Mesh | NurbsCurve): 型を解決済みのShapeラッパー。
        indices (Iterable[int]): 範囲検証済みのAPI点番号。UV番号ではない。
        edit (bool): Trueで直接編集の制限を検査する。Falseは照会用。

    Returns:
        _Geometry: ``path`` (保持DAGパス)・``fn`` (MFnMeshまたはMFnNurbsCurve)・``is_mesh`` (MeshならTrue)
            のnamedtuple。tupleとして展開できる。関数セットの取得自体では座標を書き換えない。

    Raises:
        RuntimeError: 直接編集時のロック・入力接続・書込み禁止、またはShapeを参照できない場合。
        NotImplementedError: edit=Trueで周期カーブまたはinMesh/create入力がある場合。
    """
    ...

def positions(shape: Shape, indices: Sequence[int], ws: bool = ...) -> list[tuple[float, float, float]]:
    """指定した点を保持順・cm単位で取得する。

    Args:
        shape (Shape): 有効なMeshまたはNurbsCurve。
        indices (Sequence[int]): 検証済みの点番号。
        ws (bool): Trueならワールド空間へ変換する。

    Returns:
        list[tuple[float, float, float]]: 指定順の座標。単点では全点を取得しない。
    """
    ...

def command_indices(shape: Shape, indices: Sequence[int]) -> list[int]:
    """検証済みのAPI番号をcmds用番号へ写す。順序と重複は維持する。

    Args:
        shape (Shape): MeshまたはNurbsCurve。
        indices (Sequence[int]): APIの番号。

    Returns:
        list[int]: 周期カーブでは末尾の重複CVを先頭の独立CVへ写した番号。
    """
    ...

def set_positions(shape: Shape, indices: Sequence[int], values: Sequence[Sequence[float]], ws: bool = ..., *, fast: bool = ...) -> None:
    """検証済みのcm座標を書き込む。Undo範囲は呼出元が管理する。

    Args:
        shape (Shape): MeshまたはNurbsCurve。
        indices (Sequence[int]): 検証済みのAPI番号。重複は後の値を優先。
        values (Sequence[Sequence[float]]): 番号と同数の有限なXYZ。
        ws (bool): Trueならワールド座標。
        fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

    Returns:
        None: 値を返さない。

    Raises:
        RuntimeError: Mayaが書込みを拒否した場合。完了済みの変更は戻さない。
        NotImplementedError: fastで未対応の形状の場合。
    """
    ...

def _set_positions_fast(shape: Shape, indices: Sequence[int], values: Sequence[Sequence[float]], ws: bool = ...) -> None:
    """検証済みのcm座標をOpenMayaで一括設定する。CVのwは変更しない。

    Args:
        shape (Shape): 履歴なしMeshまたは非周期NurbsCurve。
        indices (Sequence[int]): 検証済みの番号。
        values (Sequence[Sequence[float]]): 設定するXYZ。
        ws (bool): TrueならAPIワールド座標、Falseならローカル座標。

    Returns:
        None: 値を返さない。

    Raises:
        ValueError: ワールド空間で変換マトリクスが特異な場合。
        RuntimeError: ロック・入力接続・書込み禁止がある場合。
        NotImplementedError: 周期カーブまたは入力履歴のある形状の場合。
    """
    ...

def object_positions(shape: Shape, indices: Sequence[int], values: Sequence[Sequence[float]]) -> list[tuple[float, float, float]]:
    """APIのワールド座標を、CVのウェイトを保持したローカルXYZへ変換する。

    Args:
        shape (Shape): MeshまたはNurbsCurve。
        indices (Sequence[int]): 検証済みの番号。
        values (Sequence[Sequence[float]]): APIのワールドXYZ。距離はcm。

    Returns:
        list[tuple[float, float, float]]: cmdsのobjectSpaceへ渡すcmの座標。

    Raises:
        ValueError: ワールドマトリクスが特異な場合。
    """
    ...
