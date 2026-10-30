"""Maya の NURBS カーブシェイプを扱う。"""

import math
from typing import Any, Dict

import maya.api.OpenMaya as om2
import maya.cmds as cmds
from maya.api.OpenMaya import MSpace

from ..components.cv import CV, CVs
from ..core import geometryEdit as geometry_edit
from ..decorator import _edit_context, _require_bool, nativeUnits, preservedSelection, undoTransaction
from ..maths.vector import _vectors_of_points
from ..util import _world_space
from .node import Node
from .shape import Shape


class NurbsCurve(Shape):
    """NURBS カーブの形状情報を提供するシェイプラッパー。

    点列からの作成は :meth:`create`、CV位置の一括書込みは :meth:`setCvPositions` を使う。
    CV(:class:`~mlib.components.cv.CV`)の参照は読み取り専用。
    """

    @classmethod
    def create(cls, points, degree=1, closed=False, name=None, parent=None):
        """点列からNURBSカーブを作成し、そのシェイプを返す(``cmds.curve`` の特化ビルダー)。

        点をそのままCVにする(通過点の補間ではない)。開いたカーブは ``cmds.curve`` の既定ノット、
        ``closed=True`` は先頭 ``degree`` 個のCVを末尾へ重ねた周期カーブ(``getForm()`` が
        ``om2.MFnNurbsCurve.kPeriodic``)にする。形状のライブラリは持たない。作成・親子付けを1回のUndoにまとめ、現在の選択は変更しない。

        Args:
            points (Iterable[Sequence[float] | om2.MPoint | om2.MVector]): CVの位置。各点は3個の
                有限な数値(boolを除く)。MPointはwで割らずにXYZを使う。距離はMaya APIの内部単位(cm)で、
                現在のUI単位に依存しない。カーブのTransform(作成時は単位マトリクス)のローカル座標。
            degree (int): 次数。1・2・3のいずれか。既定1。
            closed (bool): Trueなら閉じたカーブにする。既定False。
            name (str | None): Transformの希望名。シェイプは ``<名前>Shape``。Noneは
                Mayaの既定名(``curve1`` 等)。衝突時はMayaが一意名にする。
            parent (Node | str | None): Transformの親。Noneはワールド直下。親のローカル空間に
                単位マトリクスで置くため、点は親の空間の座標になる。

        Returns:
            NurbsCurve: 作成したカーブのシェイプ。Transformは ``getTransform()`` で取得する
                (``mlib.createNode("nurbsCurve")`` と同じくシェイプを返す)。

        Raises:
            TypeError: points・degree・closed・nameの型が不正、または点の成分が数値でない場合。
            ValueError: degreeが1〜3でない、点の成分数が3でない・有限でない、または点の数が
                不足する場合(開いたカーブはdegree+1点以上、閉じたカーブは3点以上かつdegree点以上)。
            RuntimeError: 親が無効な場合、またはMayaが作成を拒否した場合。
        """
        values = geometry_edit.point_list(points)
        if isinstance(degree, bool) or not isinstance(degree, int):
            raise TypeError("degree must be an int")
        if degree not in (1, 2, 3):
            raise ValueError(f"degree must be 1, 2 or 3, got {degree}")
        _require_bool(closed, "closed")
        if name is not None and not isinstance(name, str):
            raise TypeError("name must be a str or None")
        if closed:
            if len(values) < max(3, degree):
                raise ValueError(f"A closed curve of degree {degree} needs at least {max(3, degree)} points")
        elif len(values) < degree + 1:
            raise ValueError(f"An open curve of degree {degree} needs at least {degree + 1} points")
        parent_node = None if parent is None else Node._resolve_input(parent)
        flags: Dict[str, Any] = {"degree": degree}
        if closed:
            count = len(values)
            values = values + values[:degree]
            # 周期カーブのノットは重なるCVの数だけ両端へはみ出す一様な列(CV数 + degree - 1 個)。
            flags["periodic"] = True
            flags["knot"] = [float(knot) for knot in range(-(degree - 1), count + degree)]
        if name:
            flags["name"] = name
        with undoTransaction("mlibNurbsCurveCreate"), preservedSelection():
            # cmds.curveの座標は現在のUI単位で解釈されるため、内部単位(cm)へ切り替えて渡す。
            with nativeUnits():
                transform = cmds.curve(point=values, **flags)
            transform = cmds.ls(transform, long=True)[0]
            if parent_node is not None:
                transform = cmds.parent(transform, parent_node.getFullName(), relative=True)[0]
                transform = cmds.ls(transform, long=True)[0]
            shape = cmds.listRelatives(transform, shapes=True, fullPath=True, type="nurbsCurve")[0]
            if name:
                # cmds.curveはTransformだけを命名するため、シェイプを <Transform名>Shape へそろえる。
                shape = cmds.rename(shape, transform.rsplit("|", 1)[-1] + "Shape")
                shape = cmds.ls(transform + "|" + shape.rsplit("|", 1)[-1], long=True)[0]
            return Node(shape)

    def getCV(self, index):
        """CV 番号から単体ラッパーを取得する。

        Args:
            index (int): ゼロ始まりの CV 番号。

        Returns:
            CV: シーン上の CV を参照するラッパー。

        Raises:
            IndexError: CV 番号が範囲外の場合。
        """
        return CV(self, index)

    def getCVs(self, indices=None):
        """OpenMayaのCV番号を入力の初出順に保持するコレクションを取得する。

        Args:
            indices (Iterable[int] | None): APIのCV番号。Noneは現在の全CVを昇順で取得し、空列は空集合。
                負数とboolは拒否する。

        Returns:
            CVs: 同じShapeを共有し、重複を除いた新しいコレクション。
                周期末尾の重複CVもAPI番号で保持するが、cmds用の名前では対応する独立CVへ写す。
        """
        return CVs(self, indices)

    def mfn(self):
        """このカーブで最も具体的な om2 function set を、呼び出すたびに新しく作って返す。

        形状データを持つ場合は ``om2.MFnNurbsCurve``。``mlib.createNode("nurbsCurve")`` 直後のように形状データを
        持たない空のシェイプは ``om2.MFnNurbsCurve`` が使えない(Maya 2027 では作成時に ValueError、
        版により作成後の照会で RuntimeError)ため、``om2.MFnDagNode`` を返す。DagNode 共通の照会
        (中間オブジェクト判定・親の列挙等)は空のシェイプでも使える。

        Returns:
            om2.MFnNurbsCurve | om2.MFnDagNode: このカーブの function set。空のシェイプでは MFnDagNode。

        Raises:
            RuntimeError: 保持する DAG パスが無効な場合。
        """
        path = self.mpath()
        try:
            fn = om2.MFnNurbsCurve(path)
            # 版により作成は通り照会で失敗するため、形状データの有無を作成直後に確かめる。
            fn.typeId
        except (RuntimeError, ValueError):
            return om2.MFnDagNode(path)
        return fn

    def getNumCVs(self):
        """CV 数を取得する。

        Returns:
            int: カーブの CV 数。
        """
        return self._geometry_fn().numCVs

    def getNumSpans(self):
        """スパン数を取得する。

        Returns:
            int: カーブのスパン数。
        """
        return self._geometry_fn().numSpans

    def getDegree(self):
        """カーブの次数を取得する。

        Returns:
            int: NURBS カーブの次数。
        """
        return self._geometry_fn().degree

    def getForm(self):
        """カーブの開閉形式を取得する。

        Returns:
            int: MFnNurbsCurve の kOpen、kClosed、kPeriodic のいずれか。
        """
        return self._geometry_fn().form

    def getLength(self, tolerance=1e-6, *, worldSpace=False, unit="cm"):
        """指定空間のカーブ長を取得する。シーンに計算ノードを作成しない。

        Args:
            tolerance (float): 弧長計算の許容誤差。内部距離単位で正の有限値。
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。
            unit (str | None): 出力単位。既定はcm。Noneは現在の距離UI単位。
                mm/cm/m/km/in/ft/yd/mi、またはMayaの長名。

        Returns:
            float: 指定単位での弧長。単位省略時はcm。
                worldSpace=Trueは親の非均等スケール・シアーとインスタンスの変換を含む。

        Raises:
            TypeError: 単位の型が不正な場合。
            ValueError: toleranceが正の有限値でない、worldSpaceがboolでない、または単位名が未対応の場合。
            RuntimeError: 無効なカーブ、またはMayaが評価を拒否した場合。
        """
        ws = _world_space(worldSpace)
        from ..common import units
        # 単位は毎回照会する。係数を使うためシーンの単位設定は変更しない。
        factor = units.convertDistance(1.0, fromUnit="cm", toUnit=unit)
        tolerance = float(tolerance)
        if not math.isfinite(tolerance) or tolerance <= 0:
            raise ValueError("tolerance must be positive and finite")
        _require_bool(ws, "worldSpace")
        if not ws:
            return self._geometry_fn().length(tolerance) * factor
        # lengthはオブジェクト空間で計算するため、メモリ内のコピーだけを
        # ワールド座標へ変換する。元のCV・履歴・Undoキューは変更しない。
        # copyにより次数・ノット・有理カーブのウェイトも維持する。
        source = self._geometry_fn()
        data = om2.MFnNurbsCurveData().create()
        copied = om2.MFnNurbsCurve().copy(source.object(), data)
        curve = om2.MFnNurbsCurve(copied)
        curve.setCVPositions(source.cvPositions(om2.MSpace.kWorld))
        curve.updateCurve()
        return curve.length(tolerance) * factor

    def getCvPositions(self, worldSpace=False):
        """CV の位置を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。

        Returns:
            list[Vector]: CV 順の位置(:class:`~mlib.maths.vector.Vector`)。距離は Maya API の
                内部単位(cm)。有理カーブのウェイト(w)は含まず、wで割らないXYZを返す。
                そのまま :meth:`setCvPositions` へ渡せる。
        """
        ws = _world_space(worldSpace)
        space = om2.MSpace.kWorld if ws else om2.MSpace.kObject
        return _vectors_of_points(self._geometry_fn().cvPositions(space))

    def setCvPositions(self, points, worldSpace=False, *, fast=False):
        """全CVの位置を一度に書き込み、自身を返す。

        :meth:`getCvPositions` と同じ並び・単位(内部単位cm)の点列を受け付け、通常は ``cmds.xform`` で
        書き込んで1回のUndoにまとめる。``fast=True`` は ``MFnNurbsCurve.setCVPositions`` で全CVを1回で
        書き込み、Undoに記録しない。CVの数・次数・ノット・ウェイトは変更しない。
        周期カーブは、独立CV数(``getNumCVs() - getDegree()``)の点列か、末尾の重複CVを含む
        ``getNumCVs()`` 個の点列(重複CVは先頭の対応CVと同じ位置であること)を受け付ける。

        Args:
            points (Iterable[Sequence[float] | om2.MPoint | om2.MVector]): CV順の位置。各点は3個の
                有限な数値。MPointはwで割らずにXYZを使う。
            worldSpace (bool): Trueはワールド空間、Falseはローカル(オブジェクト)空間。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            NurbsCurve: 自身。

        Raises:
            TypeError: worldSpace・fastがbool以外、または点の型・成分が不正な場合。
            ValueError: 点の数がCV数と合わない、成分が有限でない、周期カーブの重複CVが先頭の
                CVと一致しない、またはworldSpace=Trueで変換マトリクスが特異な場合。
            RuntimeError: 形状データが無い・無効なシェイプ、またはロック等でMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、createへの入力(コンストラクションヒストリ)がある場合。
        """
        _require_bool(fast, "fast")
        ws = _world_space(worldSpace)
        values = geometry_edit.point_list(points)
        fn = self._geometry_fn()
        count = fn.numCVs
        independent = count
        if fn.form == om2.MFnNurbsCurve.kPeriodic:
            independent = count - fn.degree
            if len(values) == count:
                for index in range(independent, count):
                    if values[index] != values[index - independent]:
                        raise ValueError("Overlapping CVs of a periodic curve must match their first CVs")
                values = values[:independent]
        if len(values) != independent:
            if independent != count:
                raise ValueError(f"Expected {independent} or {count} points, got {len(values)}")
            raise ValueError(f"Expected {count} points, got {len(values)}")
        with _edit_context("mlibNurbsCurveSetCvPositions", fast, transaction=True):
            geometry_edit.set_positions(self, list(range(independent)), values, ws, fast=fast)
        return self

    def getCollocatedCVGroups(self, tolerance=1e-6, worldSpace=False):
        """ほぼ同じ位置にある CV をグループ化して取得する。

        周期カーブの重複 CV や、クリーンアップ前のカーブの検証などに使う。

        Args:
            tolerance (float): 同一位置とみなす距離の許容誤差(Maya API の
                内部距離単位)。正の値を指定する。
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。

        Returns:
            list[list[int]]: 2個以上の CV が重なっているグループのみを、
                各グループ内は番号昇順、グループ間は先頭番号の昇順で返す。
                重なりのない単独の CV は含まない。

        Raises:
            ValueError: tolerance が正の値でない場合。
        """
        ws = _world_space(worldSpace)
        if not tolerance > 0:
            raise ValueError("tolerance must be positive")
        # 距離の計算には MPoint.distanceTo を使うため、Vector へ変換せずに om2 の点列を読む。
        positions = self._geometry_fn().cvPositions(om2.MSpace.kWorld if ws else om2.MSpace.kObject)
        assigned = [False] * len(positions)
        groups = []
        for i in range(len(positions)):
            if assigned[i]:
                continue
            group = [i]
            for j in range(i + 1, len(positions)):
                if not assigned[j] and positions[i].distanceTo(positions[j]) <= tolerance:
                    group.append(j)
                    assigned[j] = True
            if len(group) > 1:
                assigned[i] = True
                groups.append(group)
        return groups

    def _geometry_fn(self):
        """形状データを要する照会用に ``om2.MFnNurbsCurve`` を返す。

        Returns:
            om2.MFnNurbsCurve: このカーブの function set。

        Raises:
            RuntimeError: 保持する DAG パスが無効、または形状データを持たない空のシェイプの場合。
        """
        fn = self.mfn()
        if not isinstance(fn, om2.MFnNurbsCurve):
            raise RuntimeError("nurbsCurve has no geometry data: %s" % self.getFullName())
        return fn
