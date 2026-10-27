"""Maya の blendShape を扱う。"""

import json
import math
import os
import re
import tempfile
from pathlib import Path

import maya.api.OpenMaya as om2
import maya.api.OpenMayaAnim as oma2
import maya.cmds as cmds
import maya.mel as mel

from ..components.vertex import Vertex, Vertices
from ..core.attributeType import typed_data
from ..core.fastWrite import require_writable
from ..decorator import _edit_context, _require_bool, undoChunk, undoTransaction
from ..maths.vector import Vector
from .node import Node


class BlendShape(Node):
    """blendShapeノードを参照し、ターゲット・頂点マスク・デルタを照会・編集する。

    ターゲットは論理番号、weightのエイリアス、または自身のweight要素Plugで指定する。
    base省略時は原則として最小のベース論理番号を使う。getTargetIndicesだけは全ベースの和集合を返す。

    getTargetAliases/getWeightPlugs/getWeightsは全エイリアスの投影であり、
    inputTargetItemのある実ターゲットを列挙するgetTargetIndicesとは一致しないことがある。

    通常更新はcmds/MELでUndo有効時に記録する。対応するfastはUndo設定を変えずOM2で直接更新する。
    更新条件と失敗時の復旧範囲は各メソッドに従う。
    """

    def getTargetAliases(self):
        """登録された全アトリビュートエイリアス名を取得する。

        weight以外も含み、エイリアスのないターゲットは含まない。実ターゲットの有無や論理番号では絞り込まない。

        Returns:
            list[str]: getAliases()順の新しいリスト。実ターゲット番号はgetTargetIndices()で取得する。
        """
        return [alias for alias, _ in self.getAliases()]

    def getWeightPlugs(self):
        """全エイリアスの参照先Plugを、値を取得せず返す。

        weight以外も含み、エイリアスのないweight要素は含まない。

        Returns:
            list[Plug]: getAliases()順の新しいリスト。各Plugはシーンのアトリビュートへの参照。
        """
        return [plug for _, plug in self.getAliases()]

    def getWeights(self):
        """全エイリアスの現在値を取得する。

        各Plug.get()により必要ならDGを評価する。通常のweightは無次元floatで、
        それ以外の値型・単位・配列形は参照先Plug.get()に従う。

        Returns:
            list[object]: getAliases()順の新しい値リスト。エイリアスのないweight要素は含まない。
        """
        return [plug.get() for plug in self.getWeightPlugs()]

    def getGeometry(self):
        """出力に接続されたベースgeometryのShapeを参照する。

        MObjectから参照を作るため、特定のインスタンスパスは指定しない。

        Returns:
            list[Node]: getOutputGeometry()順の新しいリスト。出力がなければ空。
                ベース論理番号の昇順とは限らない。
        """
        return [Node(mobject) for mobject in oma2.MFnGeometryFilter(self.mnode()).getOutputGeometry()]

    @undoChunk("mlibBlendShapeAddTarget")
    def addTarget(self, target, base=None, weightIndex=None, fullWeight=1.0):
        """ターゲットを追加する。

        Args:
            target (Node | str | Plug | Component | om2.MObject | om2.MDagPath | om2.MPlug):
                追加するターゲット shape またはその transform。Plug・MPlug・
                ``"node.attribute"`` は所有ノード、Component は所有シェイプとして扱う。
            base (Node | str | Plug | Component | om2.MObject | om2.MDagPath | om2.MPlug | None):
                変形対象の base geometry(target と同じ規則で所有ノードへ解決する)。
                省略時は getGeometry() の先頭を使う。
            weightIndex (int | None): 使用する weight 配列番号。省略時は
                空いている最小の番号(``getPlug("weight").getNextAvailable(vacant=True)``)
                を自動で使う。
            fullWeight (float): このターゲットが完全に効いた状態(既定 1.0)の
                weight 値。

        Returns:
            Plug: 追加したターゲットの weight 要素プラグ。

        Raises:
            TypeError: target・base が対応しない型の場合。
            ValueError: target・base が空文字列、または削除済みの対象の場合。
            RuntimeError: base を省略し、かつ base geometry を特定できない場合。
                target・base の名前を解決できない場合。
        """
        target_name = Node._input_name(target)
        if base is None:
            geometries = self.getGeometry()
            if not geometries:
                raise RuntimeError("Cannot determine the base geometry for this blendShape")
            base_name = geometries[0].getFullName()
        else:
            base_name = Node._input_name(base)
        if weightIndex is None:
            weightIndex = self.getPlug("weight").getNextAvailable(vacant=True)
        cmds.blendShape(
            self.getName(), edit=True,
            target=(base_name, weightIndex, target_name, fullWeight),
        )
        return self.getPlug("weight")[weightIndex]

    @undoChunk("mlibBlendShapeRemoveTarget")
    def removeTarget(self, target):
        """全ベースからターゲットと全in-betweenを削除する。

        Maya標準のShape Editor処理で関連メタデータも削除する。
        ターゲットメッシュは削除しない。weight接続は切断され、接続元が
        combinationShapeの場合はMaya標準処理によりそのノードも削除される。

        Args:
            target (int | str | Plug): ターゲット番号またはエイリアス。

        Returns:
            BlendShape: 自身。
        """
        index = self._target_index(target)
        if self.getPlug("weight")[index].isLocked():
            raise ValueError("Locked target cannot be removed")
        if not mel.eval("blendShapeDeleteTargetGroup({}, {})".format(
                json.dumps(self.getName()), index)):
            raise RuntimeError("Maya did not remove the target")
        return self

    def addTargetDeltas(self, deltas, base=None, weightIndex=None, alias=None):
        """疎なデルタだけから、新しい通常ターゲットを登録する。

        BlendShapeへ入る変形前のgeometryを一時メッシュへ複製し、通常1.0の項目を
        登録してからデルタを設定する。一時メッシュと接続は終了時に削除を試みる。
        現在のweight・envelope・表示上の変形から中立位置を推測しない。

        Args:
            deltas (dict[int, Sequence[float]]): 頂点番号とxyz変位。通常のobject-space cm。
            base (Node | str | None): ベース。省略時は最小のベース論理番号。
            weightIndex (int | None): 未使用のweight番号。省略時は最小の空き番号。
            alias (str | None): 新しい別名。省略時はweight表記。

        Returns:
            Plug: 作成したweight要素。初期値0で、ターゲット操作へそのまま渡せる。

        Raises:
            TypeError: ポリゴンメッシュ以外のベース、またはデルタが辞書でない場合。
            ValueError: デルタ・番号・別名・入力geometryが不正、またはpost-deformation・user-defined originの場合。
            RuntimeError: Undoが無効、入力geometryを取得できない、またはMayaの編集失敗。

        Note:
            全入力を登録前に検証し、通常Undoで一回にまとめる。例外時はUndoによる巻戻しを試みる。
            復旧の二次失敗は警告し、元例外を優先する。巻戻しの完了は保証しない。
            一時ノード登録が必要なためfastフラグは提供しない。頂点順・変形前座標・
            頂点マスク等を含む全体復元にはloadTargetsを使用する。
        """
        bi = self._base_index(base)
        shape = self._base_shape(bi)
        index = self._new_index(weightIndex)
        self._require_alias(alias)
        values = self._delta_values(deltas, om2.MFnMesh(shape.mnode()).numVertices)
        if self.getPlug("origin").get() not in (0, 1) or self.getPlug("deformationOrder").get():
            raise ValueError("addTargetDeltas supports ordinary local/world-origin targets")
        geometry = typed_data(self.getPlug(f"input[{bi}].inputGeometry").mplug())
        if geometry.isNull() or not geometry.hasFn(om2.MFn.kMesh):
            raise RuntimeError("Cannot read the blendShape's undeformed input mesh")
        input_fn = om2.MFnMesh(geometry)
        topology = self._topology(shape)
        counts, connects = input_fn.getVertices()
        if (input_fn.numVertices != topology["vertices"] or list(counts) != topology["counts"]
                or list(connects) != topology["connects"]):
            raise ValueError("Input and output mesh topology differ")
        if not cmds.undoInfo(query=True, state=True):
            raise RuntimeError("addTargetDeltas requires Undo enabled")
        normalized = {vertex: point[:3] for vertex, point in values}
        with undoTransaction("mlibBlendShapeAddTargetDeltas"):
            temporary = cmds.createNode("mesh", skipSelect=True)
            neutral = Node(temporary)
            parent = neutral.getParent().getFullName()
            original_error = None
            try:
                # APIへ書くのは一時形状だけ。登録・切断・永続デルタはcmdsでUndoに記録する。
                data = om2.MFnMeshData().create()
                om2.MFnMesh().copy(geometry, data)
                neutral.getPlug("cachedInMesh").mplug().setMObject(data)
                weight = self.addTarget(neutral, base=shape, weightIndex=index)
                self.setTargetDeltas(weight, normalized, base=shape, disconnect=True)
                weight.set(0.0)
                weight.setAlias(alias)
            except BaseException as error:
                original_error = error
                raise
            finally:
                try:
                    if cmds.objExists(parent):
                        cmds.delete(parent)
                except Exception as cleanup_error:
                    if original_error is None:
                        raise
                    from .. import logger

                    logger.warning("Temporary delta target cleanup failed for %s: %s", parent, cleanup_error)
        return weight

    def getTargetIndices(self, base=None):
        """既存inputTargetItemを持つターゲットの論理番号を昇順で取得する。

        実際の出力geometryに対応するinputTargetGroupを調べる。空group、空のweight要素、
        非weightのaliasは列挙条件にならない。weight値やデルタがゼロでも項目があれば含む。

        Args:
            base (Node | str | None): ベースのMesh ShapeまたはそのTransform。
                Noneは全ベースの番号の和集合を取得する。

        Returns:
            list[int]: 重複のないターゲット論理番号。alias順や配列の物理位置ではない。
        """
        bases = self._base_indices() if base is None else [self._base_index(base)]
        return sorted({index for bi in bases
                       for index in self._existing_indices(f"inputTarget[{bi}].inputTargetGroup")
                       if self._existing_indices(
                           self._group_path(bi, index) + ".inputTargetItem")})

    def getTargetPlug(self, target):
        """登録済みターゲットに対応するweight要素のPlug参照を取得する。

        少なくとも一つのベースにinputTargetItemがあることを検査する。
        特定のベースやfullWeight項目の存在までは検査せず、weight値も取得しない。

        Args:
            target (int | str | Plug): 論理番号、weightのalias、または自身のweight要素Plug。
                boolは番号として受理せず、文字列はaliasだけを照合する。

        Returns:
            Plug: 同じweight要素への参照。値をコピーしたものではない。

        Raises:
            TypeError: targetが受理型でない場合。
            ValueError: ターゲットがない、未知のalias、または他ノード/別アトリビュートのPlug。
        """
        return self.getPlug("weight")[self._target_index(target)]

    def replaceTarget(self, target, geometry, base=None, fullWeight=1.0, *, fast=False):
        """既存ターゲット項目を別メッシュへ差し替える。

        Args:
            target (int | str | Plug): 番号またはエイリアス。
            geometry (Node | str): 新しいターゲットメッシュ。
            base (Node | str | None): ベース。省略時は先頭。
            fullWeight (float): 差し替える既存項目のウェイト。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Plug: 既存のweight要素。エイリアスと現在値を維持する。
        """
        with _edit_context("mlibBlendShapeReplaceTarget", fast):
            bi, index, item = self._resolve_item(target, base, fullWeight)
            shape = self._resolve_mesh(geometry)
            self._require_topology(bi, shape)
            # 既存項目へblendShape -targetを再発行するとMayaが拒否する。
            # 入力だけを差し替え、weight・エイリアス・ドライバ・中間形状の設定を保持する。
            source = shape.getPlug("worldMesh")[shape.mpath().instanceNumber()]
            destination = self.getPlug(self._item_path(bi, index, item) + ".inputGeomTarget")
            if fast:
                self._replace_connection(source.mplug(), destination.mplug())
            else:
                source.connectTo(destination, f=True, fast=fast)
            return self.getPlug("weight")[index]

    @undoChunk("mlibBlendShapeAddInBetween")
    def addInBetween(self, target, geometry, weight, base=None, relative=False):
        """既存ターゲットにin-betweenを追加する。

        Args:
            target (int | str | Plug): 親ターゲット番号またはエイリアス。
            geometry (Node | str): 同一トポロジーのメッシュ。
            weight (float): 0と1以外、-5以上、0.001刻みのウェイト。
            base (Node | str | None): ベース。省略時は先頭。
            relative (bool): Trueならheroターゲット相対、Falseなら絶対。

        Returns:
            Plug: 親ターゲットのweight要素。
        """
        bi, index = self._resolve_group(target, base)
        item = self._weight_item(weight)
        if item in (5000, 6000) or item in self._existing_indices(self._group_path(bi, index) + ".inputTargetItem"):
            raise ValueError("In-between weight is reserved or already exists")
        _require_bool(relative, "relative")
        shape = self._resolve_mesh(geometry)
        self._require_topology(bi, shape)
        cmds.blendShape(self.getName(), edit=True, inBetween=True,
                        inBetweenType="relative" if relative else "absolute",
                        target=(self._base_shape(bi).getFullName(), index,
                                shape.getFullName(), weight))
        return self.getPlug("weight")[index]

    @undoChunk("mlibBlendShapeRemoveInBetween")
    def removeInBetween(self, target, weight):
        """指定ウェイトのin-betweenを全ベースから削除する。

        Args:
            target (int | str | Plug): 親ターゲット番号またはエイリアス。
            weight (float): 削除する既存項目のウェイト。1は指定不可。

        Returns:
            BlendShape: 自身。
        """
        index = self._target_index(target)
        item = self._weight_item(weight)
        if item == 6000 or not any(item in self._existing_indices(
                self._group_path(bi, index) + ".inputTargetItem") for bi in self._base_indices()
                if index in self.getTargetIndices(self._base_shape(bi))):
            raise ValueError("No removable in-between at this weight")
        mel.eval("blendShapeDeleteInBetweenTarget({}, {}, {})".format(
            json.dumps(self.getName()), index, item))
        return self

    @undoChunk("mlibBlendShapeTargetEdit")
    def targetEdit(self, target=None, state=True, fullWeight=1.0):
        """ターゲットの編集モードを開始または終了する。

        Args:
            target (int | str | Plug | None): 開始する番号・エイリアス・自身のweight要素。
                開始時は必須。
                終了時は省略可能で、指定しても使用しない。
            state (bool): Trueは開始、FalseはこのblendShapeの編集を終了する。
            fullWeight (float): 編集項目のウェイト。通常1、in-betweenならその値。
                終了時は使用しない。

        Returns:
            BlendShape: 自身。

        Note:
            Maya標準sculptTargetを使用しUndoに対応する。複数ベースではノード全体に適用。
            weight値・選択・操作ツールは変更しない。fastフラグは持たない。
        """
        _require_bool(state, "state")
        if not state:
            cmds.sculptTarget(self.getName(), edit=True, target=-1)
            return self
        if target is None:
            raise ValueError("A target is required to enter edit mode")
        index = self._target_index(target)
        item = self._weight_item(fullWeight)
        if not any(item in self._existing_indices(self._group_path(bi, index) + ".inputTargetItem")
                   for bi in self._base_indices()
                   if index in self.getTargetIndices(self._base_shape(bi))):
            raise ValueError("No target item at this weight")
        cmds.sculptTarget(self.getName(), edit=True, target=index, inbetweenWeight=fullWeight)
        return self

    def getInBetweenWeights(self, target, base=None):
        """指定ベースの既存ターゲット項目から、1.0以外の項目ウェイトを取得する。

        inputTargetItemの論理番号を昇順に読み、(番号 - 5000) / 1000.0で換算する。
        6000だけを除外するため、登録経路にかかわらず1.0以外の項目を含み、
        保存されていれば0.0も含む。現在のweightアトリビュート値は参照しない。

        Args:
            target (int | str | Plug): ターゲット論理番号、weightのalias、または自身のweight要素。
            base (Node | str | None): ベースのMesh ShapeまたはそのTransform。
                Noneは最小のベース論理番号。

        Returns:
            list[float]: 無次元の項目ウェイト。選択ベースのgroupが空なら空リスト。
        """
        bi, index = self._resolve_group(target, base)
        return [(item - 5000) / 1000.0 for item in self._existing_indices(
            self._group_path(bi, index) + ".inputTargetItem") if item != 6000]

    def getTargetWeights(self, target, base=None):
        """指定ターゲットの頂点マスクを、ベースMeshの頂点番号順で取得する。

        inputTargetGroupのtargetWeightsを読み、未格納の頂点には既定値1.0を補う。
        ターゲット全体のweight値やbaseWeightsを掛けた最終変形量ではない。

        Args:
            target (int | str | Plug): ターゲット論理番号、weightのalias、または自身のweight要素。
            base (Node | str | None): ベースのMesh ShapeまたはそのTransform。
                Noneは最小のベース論理番号。

        Returns:
            list[float]: 頂点数と同じ長さの新しい値リスト。変更してもシーンへ書き戻さない。
        """
        bi, index = self._resolve_group(target, base)
        count = om2.MFnMesh(self._base_shape(bi).mnode()).numVertices
        path = self._group_path(bi, index) + ".targetWeights"
        existing = set(self._existing_indices(path))
        array = self.getPlug(path).mplug()
        return [array.elementByLogicalIndex(i).asFloat() if i in existing else 1.0
                for i in range(count)]

    def setTargetWeights(self, target, weights, base=None, *, fast=False):
        """指定ターゲットの頂点マスクtargetWeightsを更新する。

        全頂点列では頂点番号順、辞書では指定頂点だけを更新する。辞書の未指定頂点は保持し、
        未格納の指定要素は書込み時に作る。空辞書は値を変更しない。
        番号・値の有限性と列長は書込み前に検証するが、全Plugの書込み可否をまとめて
        検査するものではない。後続のロック・接続・API失敗では先行更新が残り得る。

        Args:
            target (int | str | Plug): ターゲット論理番号、weightのalias、または自身のweight要素。
            weights (Sequence[float] | dict[int, float]): 頂点数分の値、または頂点番号と値。
                番号は0以上頂点数未満のint、値は有限なint/floatとし、boolは受理しない。
                この入口では値を0〜1へ制限・正規化しない。
            base (Node | str | None): ベースのMesh ShapeまたはそのTransform。
                Noneは最小のベース論理番号。
            fast (bool): 通常は逐次cmds更新をUndo有効時に一つのチャンクへまとめる。
                Trueは逐次OpenMaya更新でUndoへ記録しない。Undo設定は変更しない。

        Returns:
            BlendShape: 自身。失敗時の自動ロールバックは行わない。

        Raises:
            ValueError: 頂点番号、値の有限性、または全頂点列の長さが不正な場合。
        """
        with _edit_context("mlibBlendShapeSetTargetWeights", fast):
            bi, index = self._resolve_group(target, base)
            count = om2.MFnMesh(self._base_shape(bi).mnode()).numVertices
            values = self._vertex_values(weights, count)
            path = self._group_path(bi, index) + ".targetWeights"
            # 配列Plugは頂点ごとに名前から解決し直さず、最初の書込みの直前に1回だけ解決する。
            array = self.getPlug(path) if values else None
            if fast:
                for vertex, value in values.items():
                    array[vertex].set(value, fast=True)
                return self
            self._set_weight_runs(array, values)
            return self

    def getTargetDeltas(self, target, base=None, fullWeight=1.0):
        """保存された疎なデルタを頂点番号とVectorの辞書で取得する。

        接続中のターゲットはMayaに評価させた現在のデルタを取得する。
        通常ターゲットではオブジェクト空間cm。inputPointsTargetの値を返し、
        相対in-betweenの補助デルタは含めない。
        post-deformationではMayaに保存された空間の値。

        Args:
            target (int | str | Plug): 番号またはエイリアス。
            base (Node | str | None): ベース。省略時は先頭。
            fullWeight (float): 取得する項目のウェイト。

        Returns:
            dict[int, Vector]: 変位を持つ頂点と変位。ゼロは省略されうる。
        """
        bi, index, item = self._resolve_item(target, base, fullWeight)
        data = self._read_item(bi, index, item)
        return {vertex: Vector(point[:3]) for vertex, point in data["absolute"]}

    def setTargetDeltas(self, target, deltas, base=None, fullWeight=1.0, disconnect=False, *, fast=False):
        """既存項目の絶対デルタ全体を置換する。省略頂点は変位ゼロになる。

        inputPointsTargetを書き換え、同項目の相対補助デルタを消去する。
        他のin-between項目のデルタは変更しない。

        Args:
            target (int | str | Plug): 番号またはエイリアス。
            deltas (dict[int, Sequence[float]]): 頂点番号とxyz変位(cm)。
            base (Node | str | None): ベース。省略時は先頭。
            fullWeight (float): 更新する既存項目のウェイト。
            disconnect (bool): Trueなら接続中のターゲット入力を切断する。
                既定では接続がある場合に変更せず拒否する。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            BlendShape: 自身。
        """
        with _edit_context("mlibBlendShapeSetTargetDeltas", fast):
            bi, index, item = self._resolve_item(target, base, fullWeight)
            _require_bool(disconnect, "disconnect")
            count = om2.MFnMesh(self._base_shape(bi).mnode()).numVertices
            values = self._delta_values(deltas, count)
            path = self._item_path(bi, index, item)
            self._disconnect_target_input(path, disconnect, fast=fast)
            self._write_deltas(path, values, fast=fast)
            # 相対補助値が残ると新しい絶対デルタと不整合になるため再計算用に空にする。
            self._write_deltas(path, [], relative=True, fast=fast)
            return self

    def resetTargetVertices(self, target, vertices, base=None, fullWeight=1.0,
                           disconnect=False, *, fast=False):
        """ターゲット項目の指定頂点の変位をゼロへ戻す。

        接続中はターゲット形状の指定頂点を中立位置へ戻して接続を維持する。
        共有ターゲット形状を利用する他の項目にも影響する。
        未接続時は残りの頂点・頂点ウェイト・他のターゲット項目を維持する。
        空入力とデルタを持たない頂点だけの指定は何も変更せず、入力接続も保持する。

        Args:
            target (int | str | Plug): ターゲット番号またはweightのエイリアス。
            vertices (int | Vertex | Vertices | Iterable[int | Vertex]): 除外する
                ベース頂点番号またはベースメッシュの頂点。重複はまとめる。
            base (Node | str | None): ベース。省略時は最小のベース論理番号。
            fullWeight (float): 除外する項目のウェイト。in-betweenも指定可能。
            disconnect (bool): 既定Falseは接続先のメッシュを自動編集する。
                Trueなら従来どおり入力を切断して保存デルタだけを編集する。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            BlendShape: 自身。
        """
        with _edit_context("mlibBlendShapeResetTargetVertices", fast):
            bi, index, item = self._resolve_item(target, base, fullWeight)
            _require_bool(disconnect, "disconnect")
            shape = self._base_shape(bi)
            if isinstance(vertices, Vertices):
                if vertices.shape.mnode() != shape.mnode():
                    raise ValueError("Vertices must belong to the selected base mesh")
                vertices = vertices.indices
            elif isinstance(vertices, (int, Vertex)):
                vertices = [vertices]
            if isinstance(vertices, (str, bytes)):
                raise TypeError("Expected vertex indices or mlib Vertex objects")
            indices = set()
            count = om2.MFnMesh(shape.mnode()).numVertices
            for vertex in vertices:
                if isinstance(vertex, Vertex):
                    if vertex.shape.mnode() != shape.mnode():
                        raise ValueError("Vertex must belong to the selected base mesh")
                    vertex = vertex.index
                self._vertex_values({vertex: 0}, count)
                indices.add(vertex)
            if not indices:
                return self
            data = self._read_item(bi, index, item)
            if not any(vertex in indices for rows in data.values() for vertex, _ in rows):
                return self
            path = self._item_path(bi, index, item)
            if not disconnect:
                sources = self.getPlug(path + ".inputGeomTarget").mplug().connectedTo(True, False)
                if sources:
                    self._remove_live_deltas(bi, index, indices, data, sources[0], fast=fast)
                    return self
            self._disconnect_target_input(path, disconnect, fast=fast)
            for key, relative in (("absolute", False), ("relative", True)):
                self._write_deltas(path, [row for row in data[key] if row[0] not in indices], relative=relative, fast=fast)
            return self

    def duplicateTarget(self, target, weightIndex=None, alias=None, *, fast=False):
        """全ベースのターゲット・in-between・頂点ウェイトを複製する。

        接続は複製せず、現在の形状をベイクする。新しいweight値は0。
        Shape Editorのフォルダ配置と外部ドライバは複製しない。

        Args:
            target (int | str | Plug): 元の番号またはエイリアス。
            weightIndex (int | None): 未使用の番号。省略時は最小の空き番号。
            alias (str | None): 新しい別名。省略時はMayaのweight表記。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Plug: 新しいターゲットのweight要素。
        """
        with _edit_context("mlibBlendShapeDuplicateTarget", fast):
            index = self._target_index(target)
            destination = self._new_index(weightIndex)
            self._require_alias(alias)
            data = self._read_target(index)
            self._write_target(destination, data, alias=alias, value=0.0, fast=fast)
            return self.getPlug("weight")[destination]

    def getTargetVertices(self, target, base=None, fullWeight=1.0, *, tolerance=0.0):
        """指定デルタの変位がしきい値を超えるベース頂点だけを取得する。

        現在のweight・envelope・頂点マスクによる変形量ではなく、
        getTargetDeltasが返す絶対デルタの長さで判定する。照会はOpenMayaを使う。

        Args:
            target (int | str | Plug): ターゲット番号またはweightのエイリアス。
            base (Node | str | None): ベース。省略時は最小のベース論理番号。
            fullWeight (float): 取得する項目のウェイト。in-betweenも指定可能。
            tolerance (float): 除外する変位長の上限。有限の非負数。
                通常ターゲットではcm。既定0は明示的に格納されたゼロも除外する。

        Returns:
            Vertices: ベースメッシュ上の頂点群。番号昇順。対象がなければ空。
        """
        if (isinstance(tolerance, bool) or not isinstance(tolerance, (int, float))
                or not math.isfinite(tolerance) or tolerance < 0):
            raise ValueError("tolerance must be a finite nonnegative number")
        bi = self._base_index(base)
        shape = self._base_shape(bi)
        deltas = self.getTargetDeltas(target, base=shape, fullWeight=fullWeight)
        return shape.getVertices(sorted(index for index, delta in deltas.items()
                                        if delta.length() > tolerance))

    def reduceTargetDeltas(self, target, tolerance=0.0, base=None, fullWeight=1.0,
                           disconnect=False, *, fast=False):
        """絶対デルタの長さがしきい値以下の頂点をターゲット項目から除外する。

        格納済みの絶対デルタを判定する。接続中はターゲット形状を自動編集する。
        未接続時は該当頂点の相対補助デルタも除外する。
        weight・envelope・頂点マスクは判定に使用しない。対象がなければ変更しない。

        Args:
            target (int | str | Plug): ターゲット番号またはweightのエイリアス。
            tolerance (float): 除外する変位長の上限。有限の非負数。
                通常ターゲットではcm。既定0はゼロデルタのみ除外する。
            base (Node | str | None): ベース。省略時は最小のベース論理番号。
            fullWeight (float): 編集する項目のウェイト。in-betweenも指定可能。
            disconnect (bool): 既定Falseは接続先のメッシュを自動編集する。
                Trueなら入力を切断して保存デルタだけを編集する。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            BlendShape: 自身。
        """
        with _edit_context("mlibBlendShapeReduceTargetDeltas", fast):
            if (isinstance(tolerance, bool) or not isinstance(tolerance, (int, float))
                    or not math.isfinite(tolerance) or tolerance < 0):
                raise ValueError("tolerance must be a finite nonnegative number")
            deltas = self.getTargetDeltas(target, base=base, fullWeight=fullWeight)
            vertices = [index for index, delta in deltas.items() if delta.length() <= tolerance]
            return self.resetTargetVertices(target, vertices, base=base, fullWeight=fullWeight,
                                           disconnect=disconnect, fast=fast)

    @undoChunk("mlibBlendShapeMirrorTarget")
    def mirrorTarget(self, target, axis="X", direction=1, base=None):
        """ターゲットの片側を反対側へミラーする(Maya標準のmirrorTarget)。

        Args:
            target (int | str | Plug): 番号またはエイリアス。
            axis (str): オブジェクト空間のX、Y、Z。
            direction (int): Maya標準方向。0=負方向、1=正方向。
            base (Node | str | None): ベース。省略時は先頭。

        Returns:
            BlendShape: 自身。接続中のターゲットは変更せず拒否する。
        """
        bi, index = self._resolve_group(target, base)
        self._require_mirror(bi, index, axis)
        if type(direction) is not int or direction not in (0, 1):
            raise ValueError("direction must be 0 or 1")
        cmds.blendShape(self.getName(), edit=True, mirrorTarget=(bi, index),
                        symmetryAxis=axis, symmetrySpace=1, mirrorDirection=direction)
        return self

    @undoChunk("mlibBlendShapeFlipTarget")
    def flipTarget(self, target, axis="X", base=None):
        """左右を交換する。左右別ターゲット作成にはduplicateTarget後に使う。

        Args:
            target (int | str | Plug): 番号またはエイリアス。
            axis (str): オブジェクト空間のX、Y、Z。
            base (Node | str | None): ベース。省略時は先頭。

        Returns:
            BlendShape: 自身。接続中のターゲットは変更せず拒否する。
        """
        bi, index = self._resolve_group(target, base)
        self._require_mirror(bi, index, axis)
        cmds.blendShape(self.getName(), edit=True, flipTarget=(bi, index),
                        symmetryAxis=axis, symmetrySpace=1)
        return self

    def dumpTargets(self, path):
        """全ターゲットをJSONへ保存する。外部接続は現在値としてベイクする。

        ポリゴンメッシュの通常(非post-deformation)ターゲットが対象。
        全ベースのトポロジー、デルタ、in-betweenメタデータ、頂点ウェイト、
        ベース頂点マスク、エイリアス、weight現在値、envelope、originを保存する。
        外部ドライバ、Shape Editorフォルダ、デフォーマの順序は保存しない。
        正規化グループ等の未対応構成は書き出し前に拒否する。

        Args:
            path (str | os.PathLike): 保存先。検証後、一時ファイルから置換する。

        Returns:
            BlendShape: 自身。
        """
        targets = {str(i): self._read_target(i) for i in self.getTargetIndices()}
        payload = {"format": "mlib.blendShape", "version": 1,
                   "bases": {str(bi): self._topology(self._base_shape(bi)) for bi in self._base_indices()},
                   "baseWeights": {str(bi): self._read_base_weights(bi) for bi in self._base_indices()},
                   "targets": targets,
                   "envelope": self.getPlug("envelope").get(),
                   "origin": self.getPlug("origin").get(),
                   "supportNegativeWeights": self.getPlug("supportNegativeWeights").get()}
        if payload["origin"] == 2:
            raise ValueError("User-defined origin is not supported by dumpTargets")
        destination = os.path.abspath(os.fspath(path))
        fd, temporary = tempfile.mkstemp(prefix=".mlib-blend-", suffix=".json",
                                         dir=Path(destination).parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
            os.replace(temporary, destination)
        finally:
            if os.path.exists(temporary):
                os.remove(temporary)
        return self

    def loadTargets(self, path, *, fast=False):
        """JSONの全ターゲットを空のblendShapeへ復元する。

        先に全データと全ベースの頂点・面接続順を検証する。ベースは保存時と
        同じ論理番号で対応させる。既存ターゲットがあれば拒否する。
        既存ノードへの追加ではなく、空のノードへの一式復元用。

        Args:
            path (str | os.PathLike): dumpTargetsで保存したJSON。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。失敗時の巻き戻しは行わない。

        Returns:
            BlendShape: 自身。通常は1回でUndoでき、失敗時はUndoによる復元を試みる。
                fast=Trueでは変更済みのデータを自動では戻さない。
        """
        _require_bool(fast, "fast")
        with open(path, encoding="utf-8") as stream:
            data = json.load(stream)
        self._require_file(data)
        if self.getTargetIndices() or self._existing_indices("weight"):
            raise ValueError("loadTargets requires an empty blendShape")
        if not fast and not cmds.undoInfo(query=True, state=True):
            raise RuntimeError("loadTargets requires Maya Undo to be enabled")
        with _edit_context("mlibBlendShapeLoadTargets", fast, transaction=True):
            for key, target in data["targets"].items():
                self._write_target(int(key), target, alias=target["alias"], value=target["value"], fast=fast)
            for attr in ("envelope", "origin", "supportNegativeWeights"):
                self.getPlug(attr).set(data[attr], fast=fast)
            for bi, weights in data["baseWeights"].items():
                for vertex, weight in enumerate(weights):
                    self.getPlug("inputTarget[{}].baseWeights[{}]".format(bi, vertex)).set(weight, fast=fast)
        return self

    def _remove_live_deltas(self, bi, index, indices, data, source, *, fast=False):
        """接続を保持し、ターゲット形状から現在の絶対変位を引く。"""
        if not source.node().hasFn(om2.MFn.kMesh):
            raise NotImplementedError("Connected target must be a mesh shape")
        origin = self.getPlug("origin").get()
        if origin not in (0, 1):
            raise NotImplementedError("User-defined origin is not supported")
        group = self._group_path(bi, index)
        if self.getPlug(group + ".postDeformersMode").get():
            raise NotImplementedError("Connected post-deformation targets cannot be edited")
        attribute = om2.MFnAttribute(source.attribute()).name
        if attribute not in ("worldMesh", "outMesh"):
            raise NotImplementedError("Target must be connected from worldMesh or outMesh")
        paths = om2.MDagPath.getAllPathsTo(source.node())
        target_path = next((path for path in paths if attribute != "worldMesh"
                            or path.instanceNumber() == source.logicalIndex()), None)
        if target_path is None:
            raise ValueError("Cannot resolve target mesh instance")
        shape = self._resolve_mesh(Node(target_path))
        self._require_topology(bi, shape)
        points = om2.MFnMesh(shape.mnode()).getPoints(om2.MSpace.kObject)
        deltas = {vertex: om2.MVector(*point[:3]) for vertex, point in data["absolute"]}
        affected = sorted(indices.intersection(deltas))
        if origin == 0:
            # Mayaの絶対デルタはベースのローカル空間。接続元の座標系へ変換する。
            matrix = self._base_shape(bi).mpath().inclusiveMatrix()
            if attribute == "worldMesh":
                target_matrix = target_path.inclusiveMatrix()
                if abs(target_matrix.det4x4()) < 1e-12:
                    raise ValueError("Target transform is singular")
                matrix = matrix * target_matrix.inverse()
            deltas = {vertex: delta * matrix for vertex, delta in deltas.items()}
        positions = [list(points[vertex] - deltas[vertex])[:3] for vertex in affected]
        shape.getVertices(affected).setPositions(positions, fast=fast)

    def _disconnect_target_input(self, path, disconnect, *, fast=False):
        """デルタ編集の入力接続ガードを共有し、明示指定時のみ切断する。"""
        destination = self.getPlug(path + ".inputGeomTarget").mplug()
        sources = destination.connectedTo(True, False)
        if sources and not disconnect:
            raise ValueError("Target geometry is connected; use disconnect=True to bake deltas")
        if sources:
            if fast:
                self._require_unlocked(destination)
                modifier = om2.MDGModifier()
                modifier.disconnect(sources[0], destination)
                modifier.doIt()
            else:
                cmds.disconnectAttr(sources[0].name(), destination.name())

    def _full_attr_name(self, path):
        """内部アトリビュートの完全名を作る。"""
        return self.getName() + "." + path

    @staticmethod
    def _set_weight_runs(array, values):
        """無単位の数値配列の要素へ、指定順を保ってcmdsで書き込む。

        指定順で番号が1ずつ増える区間は ``array[a:b]`` の範囲指定で1回のsetAttrにまとめる。
        1要素の区間は従来どおり要素Plugのsetで書く。範囲指定はロック・入力接続などで拒否されると
        範囲内のどの要素も更新しないため、その場合だけ同じ区間を要素Plugのsetで書き直し、
        拒否された要素の手前まで更新してその要素の例外を送出する(要素ごとの書込みと同じ結果)。
        Undoチャンクは呼出し側が管理する。

        Args:
            array (ArrayPlug): 書込み先の配列Plug。要素は無単位の数値アトリビュート。
            values (dict[int, float]): 検証済みの論理番号と値。挿入順に書き込む。

        Returns:
            None: 値を返さない。
        """
        runs = []
        for index, value in values.items():
            if runs and index == runs[-1][0] + len(runs[-1][1]):
                runs[-1][1].append(value)
            else:
                runs.append((index, [value]))
        name = None
        for first, row in runs:
            if len(row) == 1:
                array[first].set(row[0])
                continue
            if name is None:
                name = array.getFullName()
            try:
                cmds.setAttr(f"{name}[{first}:{first + len(row) - 1}]", *row)
            except RuntimeError:
                for position, value in enumerate(row):
                    array[first + position].set(value)

    def _existing_indices(self, path):
        """配列を確保せず既存の論理番号を取得する。"""
        return sorted(self.getPlug(path).mplug().getExistingArrayAttributeIndices())

    def _base_indices(self):
        """実際に出力ジオメトリを持つベース番号を取得する。"""
        fn = oma2.MFnGeometryFilter(self.mnode())
        return sorted(fn.indexForOutputShape(shape) for shape in fn.getOutputGeometry())

    def _base_shape(self, index):
        """番号に対応するポリゴンベースを取得する。"""
        fn = oma2.MFnGeometryFilter(self.mnode())
        return self._resolve_mesh(Node(fn.outputShapeAtIndex(index)))

    def _base_index(self, base):
        """ベースMeshを出力geometryの論理番号へ解決する。

        NoneはgetOutputGeometry()の返却順ではなく最小のベース論理番号を選ぶ。
        明示入力は所有ノードを解決し、Transformでは中間形状を除く単一Shapeを検査して
        Meshへ限定する。出力ShapeのMObject一致でベースを特定する。

        Raises:
            TypeError: 解決したShapeがポリゴンMeshでない場合。
            ValueError: ベースがない、TransformのShapeが一つでない、または登録外のgeometry。
        """
        if base is None:
            indices = self._base_indices()
            if not indices:
                raise ValueError("BlendShape has no base geometry")
            return indices[0]
        shape = self._resolve_mesh(base)
        fn = oma2.MFnGeometryFilter(self.mnode())
        for index in self._base_indices():
            if fn.outputShapeAtIndex(index) == shape.mnode():
                return index
        raise ValueError("Geometry is not a base of this blendShape")

    @staticmethod
    def _resolve_mesh(value):
        """transformまたはshapeを単一ポリゴンメッシュへ解決する。"""
        node = Node(Node._input_name(value))
        if node.mnode().hasFn(om2.MFn.kTransform):
            fn = om2.MFnDagNode(node.mpath())
            shapes = [fn.child(i) for i in range(fn.childCount())
                      if fn.child(i).hasFn(om2.MFn.kShape)
                      and not om2.MFnDagNode(fn.child(i)).isIntermediateObject]
            if len(shapes) != 1:
                raise ValueError("Expected a transform with exactly one mesh shape")
            path = node.mpath()
            path.push(shapes[0])
            node = Node._wrap_dag_path(path)
        if not node.mnode().hasFn(om2.MFn.kMesh):
            raise TypeError("This operation requires polygon mesh geometry")
        return node

    def _target_index(self, target):
        """番号・weightのalias・自身のweight要素を実ターゲット論理番号へ解決する。

        intはboolを除く。文字列はalias名だけを照合し、番号文字列やweightパスとして
        解釈しない。Plugは自身のweight配列の直下要素だけを受理する。
        存在検査は全ベースのgetTargetIndices()に対して行う。
        """
        from ..plugs.plug import Plug

        if type(target) is int:
            index = target
        elif isinstance(target, Plug):
            target._require_valid()
            mplug = target.mplug()
            if (target.getNode().mnode() != self.mnode() or not mplug.isElement or mplug.isChild
                    or mplug.array() != self.getPlug("weight").mplug()):
                raise ValueError("Target Plug must be this blendShape's weight element")
            index = mplug.logicalIndex()
        elif isinstance(target, str):
            matches = [plug.mplug().logicalIndex() for alias, plug in self.getAliases()
                       if alias == target and plug.mplug().isElement
                       and plug.getLongName() == "weight"]
            if not matches:
                raise ValueError(f"Unknown target alias: {target}")
            index = matches[0]
        else:
            raise TypeError("Target must be an integer index, alias string, or weight Plug")
        if index not in self.getTargetIndices():
            raise ValueError(f"Unknown target index: {index}")
        return index

    def _resolve_group(self, target, base):
        """ベースとターゲットを解決し、指定ベースのinputTargetGroupの存在を検査する。

        ターゲット自体は全ベースのいずれかに項目が必要だが、このベースではgroupの
        存在だけを検査する。選択groupのinputTargetItemが非空とは保証しない。

        Returns:
            tuple[int, int]: ベース論理番号とターゲット論理番号。
        """
        bi, index = self._base_index(base), self._target_index(target)
        if index not in self._existing_indices(f"inputTarget[{bi}].inputTargetGroup"):
            raise ValueError("Target does not exist on this base")
        return bi, index

    @staticmethod
    def _group_path(bi, index):
        """ターゲットグループの相対パスを取得する。"""
        return "inputTarget[{}].inputTargetGroup[{}]".format(bi, index)

    @classmethod
    def _item_path(cls, bi, index, item):
        """ターゲット項目の相対パスを取得する。"""
        return cls._group_path(bi, index) + f".inputTargetItem[{item}]"

    @staticmethod
    def _weight_item(weight):
        """項目ウェイトをMayaのinputTargetItem論理番号へ変換する。

        有限なint/floatからweight * 1000 + 5000を計算し、0〜2147483647の範囲と
        整数への差1e-6以内を検査する。boolは拒否する。5000(0.0)や6000(1.0)を
        予約値として拒否するのは呼出し側の責務であり、この変換では受理する。

        Returns:
            int: 0.001刻みの項目ウェイトに対応する論理番号。

        Raises:
            ValueError: 非有限値、bool、数値以外、範囲外、または0.001刻みで表せない場合。
        """
        if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not math.isfinite(weight):
            raise ValueError("Weight must be a finite number")
        scaled = weight * 1000.0 + 5000
        if scaled < 0 or scaled > 2147483647 or abs(scaled - round(scaled)) > 1e-6:
            raise ValueError("Weight must be >= -5 and representable in steps of 0.001")
        return int(round(scaled))

    def _resolve_item(self, target, base, weight):
        """実在するターゲット項目だけを解決する。"""
        bi, index = self._resolve_group(target, base)
        item = self._weight_item(weight)
        if item not in self._existing_indices(self._group_path(bi, index) + ".inputTargetItem"):
            raise ValueError("Target item does not exist at this weight")
        return bi, index, item

    @staticmethod
    def _topology(shape):
        """頂点数と面頂点接続順をJSON互換形式で取得する。"""
        fn = om2.MFnMesh(shape.mnode())
        counts, vertices = fn.getVertices()
        return {"vertices": fn.numVertices, "counts": list(counts), "connects": list(vertices)}

    def _require_topology(self, bi, shape):
        """番号まで同一のトポロジーであることを確認する。"""
        if self._topology(self._base_shape(bi)) != self._topology(shape):
            raise ValueError("Mesh topology differs from the base")

    @staticmethod
    def _vertex_values(weights, count):
        """頂点番号と有限なウェイトを全件検証する。"""
        if isinstance(weights, dict):
            values = dict(weights)
        else:
            values = dict(enumerate(weights))
            if len(values) != count:
                raise ValueError("Expected one weight per vertex")
        if any(type(i) is not int or i < 0 or i >= count for i in values):
            raise ValueError("Vertex index outside mesh")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
               for v in values.values()):
            raise ValueError("Vertex weights must be finite numbers")
        return values

    @classmethod
    def _delta_values(cls, deltas, count):
        """疎なデルタ辞書を検証しpointArray形式に変換する。"""
        if not isinstance(deltas, dict):
            raise TypeError("Deltas must be a vertex-index dictionary")
        cls._vertex_values({i: 0 for i in deltas}, count)
        result = []
        for vertex, delta in sorted(deltas.items()):
            xyz = list(delta)
            if len(xyz) != 3 or any(isinstance(v, bool) or not isinstance(v, (int, float))
                                   or not math.isfinite(v) for v in xyz):
                raise ValueError("Each delta must contain three finite numbers")
            result.append([vertex, xyz + [1.0]])
        return result

    def _read_item(self, bi, index, item):
        """Mayaが保持する絶対・相対デルタを取得する。"""
        path = self._item_path(bi, index, item)
        result = {}
        for key, prefix in (("absolute", "input"), ("relative", "inputRelative")):
            points_object = typed_data(self.getPlug(path + "." + prefix + "PointsTarget").mplug())
            points = [] if points_object.isNull() else om2.MFnPointArrayData(points_object).array()
            components_object = typed_data(self.getPlug(path + "." + prefix + "ComponentsTarget").mplug())
            vertices = []
            if not components_object.isNull():
                components = om2.MFnComponentListData(components_object)
                for i in range(components.length()):
                    component = components.get(i)
                    if component.apiType() != om2.MFn.kMeshVertComponent:
                        raise ValueError("Only polygon vertex deltas are supported")
                    fn = om2.MFnSingleIndexedComponent(component)
                    vertices.extend(range(fn.getCompleteData()) if fn.isComplete else fn.getElements())
            if len(vertices) != len(points):
                raise ValueError("Maya returned inconsistent target delta arrays")
            result[key] = [[vertex, [point.x, point.y, point.z, point.w]]
                           for vertex, point in zip(vertices, points)]
        return result

    def _write_deltas(self, path, values, relative=False, *, fast=False):
        """通常はsetAttr、fastではMFnデータとMPlugでデルタを設定する。"""
        prefix = "inputRelative" if relative else "input"
        if fast:
            points_plug = self.getPlug(path + "." + prefix + "PointsTarget").mplug()
            components_plug = self.getPlug(path + "." + prefix + "ComponentsTarget").mplug()
            require_writable(points_plug)
            require_writable(components_plug)
            component_list = om2.MFnComponentListData()
            components = component_list.create()
            if values:
                fn = om2.MFnSingleIndexedComponent()
                component = fn.create(om2.MFn.kMeshVertComponent)
                fn.addElements([vertex for vertex, _ in values])
                component_list.add(component)
            points = om2.MFnPointArrayData().create([om2.MPoint(point) for _, point in values])
            points_plug.setMObject(points)
            components_plug.setMObject(components)
            return
        cmds.setAttr(self._full_attr_name(path + "." + prefix + "PointsTarget"), len(values),
                     *[point for _, point in values], type="pointArray")
        cmds.setAttr(self._full_attr_name(path + "." + prefix + "ComponentsTarget"), len(values),
                     *[f"vtx[{vertex}]" for vertex, _ in values], type="componentList")

    def _new_index(self, index):
        """既存weightとターゲットを上書きしない番号を選ぶ。"""
        used = set(self.getTargetIndices()) | set(self._existing_indices("weight"))
        if index is None:
            index = 0
            while index in used:
                index += 1
        if type(index) is not int or not 0 <= index <= 2147483647 or index in used:
            raise ValueError("Expected an unused nonnegative target index")
        return index

    def _require_alias(self, alias):
        """別名の構文と既存アトリビュートとの衝突を検証する。"""
        if alias is not None and (not isinstance(alias, str)
                                  or not re.fullmatch(r"[^\W\d]\w*(?::[^\W\d]\w*)*", alias)
                                  or self.hasAttr(alias)):
            raise ValueError("Alias is invalid or already exists")

    def _require_mirror(self, bi, index, axis):
        """ミラー条件と接続のないデルタであることを確認する。"""
        self._base_shape(bi)
        if axis not in ("X", "Y", "Z"):
            raise ValueError("axis must be X, Y, or Z")
        for item in self._existing_indices(self._group_path(bi, index) + ".inputTargetItem"):
            if self.getPlug(self._item_path(bi, index, item) + ".inputGeomTarget").mplug().isDestination:
                raise ValueError("Mirror requires baked targets; duplicateTarget first")

    def _read_target(self, index):
        """複製と保存に共通のターゲットデータを取得する。"""
        aliases = {plug.mplug().logicalIndex(): alias for alias, plug in self.getAliases()
                   if plug.mplug().isElement and plug.getLongName() == "weight"}
        result = {"alias": aliases.get(index),
                  "value": self.getPlug("weight")[index].get() if index in self._existing_indices("weight") else 0.0,
                  "bases": {}, "inbetweens": {}}
        for bi in self._base_indices():
            group = self._group_path(bi, index)
            if index not in self._existing_indices(f"inputTarget[{bi}].inputTargetGroup"):
                continue
            if any(self.getPlug(group + "." + attr).get() != 0
                   for attr in ("postDeformersMode", "normalizationId")):
                raise ValueError("Post-deformation and normalization groups are not supported")
            result["bases"][str(bi)] = {
                "weights": self.getTargetWeights(index, self._base_shape(bi)),
                "items": {str(item): self._read_item(bi, index, item) for item in
                          self._existing_indices(group + ".inputTargetItem")}}
        if index in self._existing_indices("inbetweenInfoGroup"):
            root = f"inbetweenInfoGroup[{index}].inbetweenInfo"
            for item in self._existing_indices(root):
                path = root + f"[{item}]"
                metadata = {attr: self.getPlug(path + "." + attr).get() for attr in
                            ("inbetweenTargetType", "inbetweenTargetName", "interpolation", "inbetweenVisibility")}
                metadata["inbetweenTargetName"] = metadata["inbetweenTargetName"] or "IB"
                metadata["curve"] = {str(i): list(self.getPlug(
                    path + f".interpolationCurve[{i}]").get())
                    for i in self._existing_indices(path + ".interpolationCurve")}
                result["inbetweens"][str(item)] = metadata
        return result

    def _read_base_weights(self, bi):
        """ベースの頂点マスクを既定値を補って取得する。"""
        count = om2.MFnMesh(self._base_shape(bi).mnode()).numVertices
        path = f"inputTarget[{bi}].baseWeights"
        existing = set(self._existing_indices(path))
        array = self.getPlug(path).mplug()
        return [array.elementByLogicalIndex(i).asFloat() if i in existing else 1.0
                for i in range(count)]

    def _write_target(self, index, data, alias, value, *, fast=False):
        """検証済みスナップショットを未使用番号へ書き込む。"""
        # setAttrだけで未確保の配列を作ると、Undo後も空のグループが残る。
        # Maya標準のターゲット追加で構造を作り、一時形状を削除してからデルタを復元する。
        for bi, group in data["bases"].items():
            if not fast:
                temporary = cmds.duplicate(self._base_shape(int(bi)).getFullName(),
                                           returnRootsOnly=True)[0]
                try:
                    cmds.blendShape(self.getName(), edit=True, target=(
                        self._base_shape(int(bi)).getFullName(), index, temporary, 1.0))
                finally:
                    cmds.delete(temporary)
            for item, payload in group["items"].items():
                path = self._item_path(int(bi), index, int(item))
                self._write_deltas(path, payload["absolute"], fast=fast)
                self._write_deltas(path, payload["relative"], relative=True, fast=fast)
            if not fast and "6000" not in group["items"]:
                cmds.removeMultiInstance(self._full_attr_name(self._item_path(int(bi), index, 6000)), b=True)
            path = self._group_path(int(bi), index) + ".targetWeights"
            array = None
            for vertex, weight in enumerate(group["weights"]):
                if weight != 1.0:
                    if array is None:
                        # 頂点ごとに名前から解決し直さず、最初の書込みの直前に1回だけ解決する。
                        array = self.getPlug(path)
                    array[vertex].set(weight, fast=fast)
        for item, metadata in data["inbetweens"].items():
            path = "inbetweenInfoGroup[{}].inbetweenInfo[{}]".format(index, item)
            for attr, metadata_value in metadata.items():
                if attr == "curve":
                    for ci, pair in metadata_value.items():
                        self.getPlug(path + f".interpolationCurve[{ci}]").set(pair, fast=fast)
                else:
                    self.getPlug(path + "." + attr).set(metadata_value, fast=fast)
        plug = self.getPlug("weight")[index]
        plug.set(value, fast=fast)
        if fast:
            # MFnDependencyNodeによる別名更新もUndoキューを使わない。
            fn = self._dependency_fn()
            name = f"weight[{index}]"
            if alias and not fn.setAlias(alias, name, plug.mplug(), True):
                raise RuntimeError("Could not set target alias")
        else:
            plug.setAlias(None, fast=fast)
            if alias:
                plug.setAlias(alias, fast=fast)

    @staticmethod
    def _require_unlocked(plug):
        """入力接続の切断前に所有ノードと親を含むロックを検査する。"""
        if om2.MFnDependencyNode(plug.node()).isLocked:
            raise RuntimeError(f"Node is locked: {plug.name()}")
        current = plug
        while True:
            if current.isLocked:
                raise RuntimeError(f"Attribute is locked: {plug.name()}")
            if current.isChild:
                current = current.parent()
            elif current.isElement:
                current = current.array()
            else:
                break

    @staticmethod
    def _replace_connection(source, destination):
        """OpenMayaで接続を置換し、通常のforce接続と同様にロックを戻す。"""
        if om2.MFnDependencyNode(destination.node()).isLocked:
            raise RuntimeError(f"Node is locked: {destination.name()}")
        sources = destination.connectedTo(True, False)
        if sources and sources[0] == source:
            raise RuntimeError(f"Already connected: {destination.name()}")
        locked = []
        current = destination
        while True:
            if current.isLocked:
                locked.append(current)
            if current.isChild:
                current = current.parent()
            elif current.isElement:
                current = current.array()
            else:
                break
        try:
            for plug in reversed(locked):
                plug.isLocked = False
            modifier = om2.MDGModifier()
            if sources:
                modifier.disconnect(sources[0], destination)
            modifier.connect(source, destination)
            modifier.doIt()
        finally:
            for plug in locked:
                plug.isLocked = True

    def _require_file(self, data):
        """ファイル全体を検証し任意のアトリビュート書き込みを防止する。"""
        if not isinstance(data, dict) or data.get("format") != "mlib.blendShape" or data.get("version") != 1:
            raise ValueError("Unsupported blendShape file")
        expected = {str(bi): self._topology(self._base_shape(bi)) for bi in self._base_indices()}
        if data.get("bases") != expected:
            raise ValueError("Base indices or mesh topology do not match")
        if not isinstance(data.get("baseWeights"), dict) or set(data["baseWeights"]) != set(expected):
            raise ValueError("Base weights do not match geometry")
        for bi, weights in data["baseWeights"].items():
            if not isinstance(weights, list):
                raise ValueError("Expected a full base weight list")
            self._vertex_values(weights, expected[bi]["vertices"])
        if data.get("origin") not in (0, 1) or type(data.get("supportNegativeWeights")) is not bool:
            raise ValueError("Invalid blendShape settings")
        self._vertex_values({0: data.get("envelope")}, 1)
        aliases = set()
        for key, target in data["targets"].items():
            self._file_index(key)
            alias = target["alias"]
            self._require_alias(alias)
            if alias and alias in aliases:
                raise ValueError("Duplicate target alias")
            aliases.add(alias)
            self._vertex_values({0: target["value"]}, 1)
            if not target["bases"] or set(target["bases"]) - set(expected):
                raise ValueError("Unknown or missing target bases")
            for bi, group in target["bases"].items():
                count = expected[bi]["vertices"]
                if not isinstance(group["weights"], list):
                    raise ValueError("Expected full vertex weight list")
                self._vertex_values(group["weights"], count)
                if not group["items"]:
                    raise ValueError("Target has no items")
                for item, payload in group["items"].items():
                    self._file_index(item)
                    if set(payload) != {"absolute", "relative"}:
                        raise ValueError("Invalid delta payload")
                    for rows in payload.values():
                        vertices = set()
                        for vertex, point in rows:
                            if vertex in vertices or len(point) != 4 or point[3] != 1.0:
                                raise ValueError("Invalid or duplicate delta")
                            vertices.add(vertex)
                            self._delta_values({vertex: point[:3]}, count)
            for item, metadata in target["inbetweens"].items():
                self._file_index(item)
                if set(metadata) != {"inbetweenTargetType", "inbetweenTargetName", "interpolation",
                                     "inbetweenVisibility", "curve"}:
                    raise ValueError("Invalid in-between metadata")
                if metadata["inbetweenTargetType"] not in (0, 1) or not isinstance(metadata["inbetweenTargetName"], str):
                    raise ValueError("Invalid in-between type/name")
                if type(metadata["interpolation"]) is not int or not 0 <= metadata["interpolation"] <= 3:
                    raise ValueError("Invalid interpolation")
                if type(metadata["inbetweenVisibility"]) is not bool:
                    raise ValueError("Invalid visibility")
                for ci, pair in metadata["curve"].items():
                    self._file_index(ci)
                    if len(pair) != 2:
                        raise ValueError("Invalid interpolation curve")
                    self._vertex_values(pair, 2)

    @staticmethod
    def _file_index(value):
        """外部ファイル内の番号を安全な正規化済み文字列に制限する。"""
        if not isinstance(value, str) or not re.fullmatch(r"0|[1-9][0-9]*", value) or int(value) > 2147483647:
            raise ValueError("Invalid index in blendShape file")
