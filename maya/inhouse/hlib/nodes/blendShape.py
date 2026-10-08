"""Maya の blendShape を扱う。"""

import json
import math
import os
import re
import tempfile
from contextlib import nullcontext

import maya.api.OpenMaya as om2
import maya.api.OpenMayaAnim as oma2
import maya.cmds as cmds
import maya.mel as mel

from .._core.attributeType import typed_data
from .._core.fastWrite import writable
from .._core.getterAlias import _getter_alias
from ..common._fast import fast_edit, is_fast
from ..components.vertex import Vertex, Vertices
from ..decorator import undoChunk, undoTransaction
from ..maths.vector import Vector
from .node import Node


class BlendShape(Node):
    """MayaのblendShape。ターゲット編集・頂点ウェイト・デルタ・保存復元を扱う。

    照会はOpenMaya、通常更新はUndo可能なcmds/MELを使用する。
    fast対応メソッドは直接更新に切り替え、Undoへ記録しない。
    API 2.0にはMFnBlendShapeDeformerがなく、追加・削除・ミラーの
    Maya標準処理はcmds/MELを維持する。
    """

    def getTargetAliases(self):
        """ノードのエイリアス名を getAliases() の順序で取得する。

        通常はターゲットの weight のエイリアスだが、他のアトリビュートのエイリアスも
        含む。weight の論理インデックスによる並べ替えや絞り込みは行わない。

        Returns:
            list[str]: エイリアス名(既定ではターゲット shape の
                トランスフォーム名)。
        """
        return [alias for alias, _ in self.getAliases()]

    def getWeightPlugs(self):
        """エイリアスが付いたプラグを getTargetAliases() と同じ順序で取得する。

        weight 以外にエイリアスを設定した場合、そのプラグも含む。

        Returns:
            list[Plug]: getTargetAliases() と同じ順序のプラグ。set() で値を変更できる。
        """
        return [plug for _, plug in self.getAliases()]

    def getWeights(self):
        """getWeightPlugs() が返すプラグの現在値を取得する。

        Returns:
            list[object]: getTargetAliases() と同じ順序の値。通常の weight は float。
                weight 以外のエイリアスがある場合は、そのプラグの値も含む。
        """
        return [plug.get() for plug in self.getWeightPlugs()]

    def getGeometry(self):
        """変形対象の base geometry shape を取得する。

        Returns:
            list[Node]: 変形対象の shape。無ければ空リスト。
        """
        return [Node(mobject) for mobject in oma2.MFnGeometryFilter(self.mnode()).getOutputGeometry()]

    @undoChunk("hlibBlendShapeAddTarget")
    def addTarget(self, target, base=None, weight_index=None, full_weight=1.0):
        """ターゲットを追加する。

        Args:
            target (Node | str | Plug | Component | om2.MObject | om2.MDagPath | om2.MPlug):
                追加するターゲット shape またはその transform。Plug・MPlug・
                ``"node.attribute"`` は所有ノード、Component は所有シェイプとして扱う。
            base (Node | str | Plug | Component | om2.MObject | om2.MDagPath | om2.MPlug | None):
                変形対象の base geometry(target と同じ規則で所有ノードへ解決する)。
                省略時は getGeometry() の先頭を使う。
            weight_index (int | None): 使用する weight 配列インデックス。省略時は
                空いている最小のインデックス(``getPlug("weight").getNextAvailableIndex()``)
                を自動で使う。
            full_weight (float): このターゲットが完全に効いた状態(既定 1.0)の
                weight 値。

        Returns:
            Plug: 追加したターゲットの weight 要素プラグ。

        Raises:
            RuntimeError: base を省略し、かつ base geometry を特定できない場合。
                target・base の名前を解決できない場合。
            TypeError: target・base が対応しない型の場合。
            ValueError: target・base が空文字列、または削除済みの対象の場合。
        """
        from .node import Node as _InputNode
        target_name = _InputNode._input_name(target)
        if base is None:
            geometries = self.getGeometry()
            if not geometries:
                raise RuntimeError("Cannot determine the base geometry for this blendShape")
            base_name = geometries[0].getFullName()
        else:
            base_name = _InputNode._input_name(base)
        if weight_index is None:
            weight_index = self.getPlug("weight").getNextAvailableIndex()
        cmds.blendShape(
            self.getName(), edit=True,
            target=(base_name, weight_index, target_name, full_weight),
        )
        return self.getPlug("weight")[weight_index]

    @undoChunk("hlibBlendShapeRemoveTarget")
    def removeTarget(self, target):
        """全ベースからターゲットと全in-betweenを削除する。

        Maya標準のShape Editor処理で関連メタデータも削除する。
        ターゲットメッシュは削除しない。weight接続は切断され、接続元が
        combinationShapeの場合はMaya標準処理によりそのノードも削除される。

        Args:
            target (int | str): ターゲット番号またはエイリアス。

        Returns:
            BlendShape: 自身。
        """
        index = self._target_index(target)
        if self.getPlug("weight")[index].isLocked():
            raise ValueError("Locked target cannot be removed")
        if not mel.eval('blendShapeDeleteTargetGroup({}, {})'.format(
                json.dumps(self.getName()), index)):
            raise RuntimeError("Maya did not remove the target")
        return self

    def getTargetIndices(self, base=None):
        """実在するターゲットの論理インデックスを昇順で取得する。

        Args:
            base (Node | str | None): ベース。省略時は全ベースの和集合。

        Returns:
            list[int]: weight以外のエイリアスと空のweight要素を除いた番号。
        """
        bases = self._base_indices() if base is None else [self._base_index(base)]
        return sorted({index for bi in bases
                       for index in self._indices("inputTarget[{}].inputTargetGroup".format(bi))
                       if self._indices(
                           self._group_path(bi, index) + ".inputTargetItem")})

    def getTargetPlug(self, target):
        """ターゲット番号またはweightのエイリアスからPlugを取得する。

        Args:
            target (int | str): 実在するターゲット番号またはエイリアス。

        Returns:
            Plug: 対応するweight要素。
        """
        return self.getPlug("weight")[self._target_index(target)]

    @fast_edit
    @undoChunk("hlibBlendShapeReplaceTarget")
    def replaceTarget(self, target, geometry, base=None, full_weight=1.0, *, fast=False):
        """既存ターゲット項目を別メッシュへ差し替える。

        Args:
            target (int | str): 番号またはエイリアス。
            geometry (Node | str): 新しいターゲットメッシュ。
            base (Node | str | None): ベース。省略時は先頭。
            full_weight (float): 差し替える既存項目のウェイト。
            fast (bool): TrueはOpenMaya直接更新。Undoには記録しない。

        Returns:
            Plug: 既存のweight要素。エイリアスと現在値を維持する。
        """
        bi, index, item = self._item(target, base, full_weight)
        shape = self._mesh(geometry)
        self._check_topology(bi, shape)
        # 既存項目へblendShape -targetを再発行するとMayaが拒否する。
        # 入力だけを差し替え、weight・エイリアス・ドライバ・中間形状の設定を保持する。
        source = shape.getPlug("worldMesh")[shape.mpath().instanceNumber()]
        destination = self.getPlug(self._item_path(bi, index, item) + ".inputGeomTarget")
        if is_fast():
            self._replace_connection(source.mplug(), destination.mplug())
        else:
            source.connectTo(destination, f=True)
        return self.getPlug("weight")[index]

    @undoChunk("hlibBlendShapeAddInBetween")
    def addInBetween(self, target, geometry, weight, base=None, relative=False):
        """既存ターゲットにin-betweenを追加する。

        Args:
            target (int | str): 親ターゲット番号またはエイリアス。
            geometry (Node | str): 同一トポロジーのメッシュ。
            weight (float): 0と1以外、-5以上、0.001刻みのウェイト。
            base (Node | str | None): ベース。省略時は先頭。
            relative (bool): Trueならheroターゲット相対、Falseなら絶対。

        Returns:
            Plug: 親ターゲットのweight要素。
        """
        bi, index = self._group(target, base)
        item = self._weight_item(weight)
        if item in (5000, 6000) or item in self._indices(self._group_path(bi, index) + ".inputTargetItem"):
            raise ValueError("In-between weight is reserved or already exists")
        if type(relative) is not bool:
            raise TypeError("relative must be bool")
        shape = self._mesh(geometry)
        self._check_topology(bi, shape)
        cmds.blendShape(self.getName(), edit=True, inBetween=True,
                        inBetweenType="relative" if relative else "absolute",
                        target=(self._base_shape(bi).getFullName(), index,
                                shape.getFullName(), weight))
        return self.getPlug("weight")[index]

    @undoChunk("hlibBlendShapeRemoveInBetween")
    def removeInBetween(self, target, weight):
        """指定ウェイトのin-betweenを全ベースから削除する。

        Args:
            target (int | str): 親ターゲット番号またはエイリアス。
            weight (float): 削除する既存項目のウェイト。1は指定不可。

        Returns:
            BlendShape: 自身。
        """
        index = self._target_index(target)
        item = self._weight_item(weight)
        if item == 6000 or not any(item in self._indices(
                self._group_path(bi, index) + ".inputTargetItem") for bi in self._base_indices()
                if index in self.getTargetIndices(self._base_shape(bi))):
            raise ValueError("No removable in-between at this weight")
        mel.eval('blendShapeDeleteInBetweenTarget({}, {}, {})'.format(
            json.dumps(self.getName()), index, item))
        return self

    @undoChunk("hlibBlendShapeTargetEdit")
    def targetEdit(self, target=None, state=True, full_weight=1.0):
        """ターゲットの編集モードを開始または終了する。

        Args:
            target (int | str | None): 開始する番号またはエイリアス。開始時は必須。
                終了時は省略可能で、指定しても使用しない。
            state (bool): Trueは開始、FalseはこのblendShapeの編集を終了する。
            full_weight (float): 編集項目のウェイト。通常1、in-betweenならその値。
                終了時は使用しない。

        Returns:
            BlendShape: 自身。

        Maya標準sculptTargetを使用しUndoに対応する。複数ベースではノード全体に適用。
        weight値・選択・操作ツールは変更しない。fastフラグは持たない。
        """
        if type(state) is not bool:
            raise TypeError("state must be bool")
        if not state:
            cmds.sculptTarget(self.getName(), edit=True, target=-1)
            return self
        if target is None:
            raise ValueError("A target is required to enter edit mode")
        index = self._target_index(target)
        item = self._weight_item(full_weight)
        if not any(item in self._indices(self._group_path(bi, index) + ".inputTargetItem")
                   for bi in self._base_indices()
                   if index in self.getTargetIndices(self._base_shape(bi))):
            raise ValueError("No target item at this weight")
        cmds.sculptTarget(self.getName(), edit=True, target=index, inbetweenWeight=full_weight)
        return self

    def getInBetweenWeights(self, target, base=None):
        """hero(1.0)以外の項目ウェイトを昇順で取得する。

        Args:
            target (int | str): 親ターゲット番号またはエイリアス。
            base (Node | str | None): ベース。省略時は先頭。

        Returns:
            list[float]: 既存のin-betweenウェイト。
        """
        bi, index = self._group(target, base)
        return [(item - 5000) / 1000.0 for item in self._indices(
            self._group_path(bi, index) + ".inputTargetItem") if item != 6000]

    def getTargetWeights(self, target, base=None):
        """ターゲットの頂点別ウェイトを取得する。

        Args:
            target (int | str): 番号またはエイリアス。
            base (Node | str | None): ベース。省略時は先頭。

        Returns:
            list[float]: 頂点番号順。未格納の頂点は既定値1.0。
        """
        bi, index = self._group(target, base)
        count = om2.MFnMesh(self._base_shape(bi).mnode()).numVertices
        path = self._group_path(bi, index) + ".targetWeights"
        existing = set(self._indices(path))
        array = self.getPlug(path).mplug()
        return [array.elementByLogicalIndex(i).asFloat() if i in existing else 1.0
                for i in range(count)]

    @fast_edit
    @undoChunk("hlibBlendShapeSetTargetWeights")
    def setTargetWeights(self, target, weights, base=None, *, fast=False):
        """頂点別ウェイトを設定する。全頂点列または部分更新の辞書を受け付ける。

        Args:
            target (int | str): 番号またはエイリアス。
            weights (Sequence[float] | dict[int, float]): 全頂点列または頂点番号と値。
            base (Node | str | None): ベース。省略時は先頭。
            fast (bool): TrueはOpenMaya直接更新。Undoには記録しない。

        Returns:
            BlendShape: 自身。入力全体を検証してから変更する。
        """
        bi, index = self._group(target, base)
        count = om2.MFnMesh(self._base_shape(bi).mnode()).numVertices
        values = self._vertex_values(weights, count)
        path = self._group_path(bi, index) + ".targetWeights"
        for vertex, value in values.items():
            self.getPlug(path)[vertex].set(value)
        return self

    def getTargetDeltas(self, target, base=None, full_weight=1.0):
        """保存された疎なデルタを頂点番号とVectorの辞書で取得する。

        接続中のターゲットはMayaに評価させた現在のデルタを取得する。
        通常ターゲットではオブジェクト空間cm。inputPointsTargetの値を返し、
        相対in-betweenの補助デルタは含めない。
        post-deformationではMayaに保存された空間の値。

        Args:
            target (int | str): 番号またはエイリアス。
            base (Node | str | None): ベース。省略時は先頭。
            full_weight (float): 取得する項目のウェイト。

        Returns:
            dict[int, Vector]: 変位を持つ頂点と変位。ゼロは省略されうる。
        """
        bi, index, item = self._item(target, base, full_weight)
        data = self._read_item(bi, index, item)
        return {vertex: Vector(point[:3]) for vertex, point in data["absolute"]}

    @fast_edit
    @undoChunk("hlibBlendShapeSetTargetDeltas")
    def setTargetDeltas(self, target, deltas, base=None, full_weight=1.0, disconnect=False, *, fast=False):
        """既存項目の絶対デルタ全体を置換する。省略頂点は変位ゼロになる。

        inputPointsTargetを書き換え、同項目の相対補助デルタを消去する。
        他のin-between項目のデルタは変更しない。

        Args:
            target (int | str): 番号またはエイリアス。
            deltas (dict[int, Sequence[float]]): 頂点番号とxyz変位(cm)。
            base (Node | str | None): ベース。省略時は先頭。
            full_weight (float): 更新する既存項目のウェイト。
            disconnect (bool): Trueなら接続中のターゲット入力を切断する。
                既定では接続がある場合に変更せず拒否する。
            fast (bool): TrueはOpenMaya直接更新。Undoには記録しない。

        Returns:
            BlendShape: 自身。
        """
        bi, index, item = self._item(target, base, full_weight)
        if type(disconnect) is not bool:
            raise TypeError("disconnect must be bool")
        count = om2.MFnMesh(self._base_shape(bi).mnode()).numVertices
        values = self._delta_values(deltas, count)
        path = self._item_path(bi, index, item)
        self._disconnect_target_input(path, disconnect)
        self._write_deltas(path, values)
        # 相対補助値が残ると新しい絶対デルタと不整合になるため再計算用に空にする。
        self._write_deltas(path, [], relative=True)
        return self

    @fast_edit
    @undoChunk("hlibBlendShapeResetTargetVertices")
    def resetTargetVertices(self, target, vertices, base=None, full_weight=1.0,
                           disconnect=False, *, fast=False):
        """ターゲット項目の指定頂点の変位をゼロへ戻す。

        接続中はターゲット形状の指定頂点を中立位置へ戻して接続を維持する。
        共有ターゲット形状を利用する他の項目にも影響する。
        未接続時は残りの頂点・頂点ウェイト・他のターゲット項目を維持する。
        空入力とデルタを持たない頂点だけの指定は何も変更せず、入力接続も保持する。

        Args:
            target (int | str): ターゲット番号またはweightのエイリアス。
            vertices (int | Vertex | Vertices | Iterable[int | Vertex]): 除外する
                ベース頂点番号またはベースメッシュの頂点。重複はまとめる。
            base (Node | str | None): ベース。省略時は最小のベース論理番号。
            full_weight (float): 除外する項目のウェイト。in-betweenも指定可能。
            disconnect (bool): 既定Falseは接続先のメッシュを自動編集する。
                Trueなら従来どおり入力を切断して保存デルタだけを編集する。
            fast (bool): TrueはOpenMaya直接更新。Undoには記録しない。

        Returns:
            BlendShape: 自身。
        """
        bi, index, item = self._item(target, base, full_weight)
        if type(disconnect) is not bool:
            raise TypeError("disconnect must be bool")
        shape = self._base_shape(bi)
        if isinstance(vertices, Vertices):
            if vertices.shape.mnode() != shape.mnode():
                raise ValueError("Vertices must belong to the selected base mesh")
            vertices = vertices.indices
        elif isinstance(vertices, (int, Vertex)):
            vertices = [vertices]
        if isinstance(vertices, (str, bytes)):
            raise TypeError("Expected vertex indices or hlib Vertex objects")
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
                self._remove_live_deltas(bi, index, indices, data, sources[0])
                return self
        self._disconnect_target_input(path, disconnect)
        for key, relative in (("absolute", False), ("relative", True)):
            self._write_deltas(path, [row for row in data[key] if row[0] not in indices], relative=relative)
        return self

    @fast_edit
    @undoChunk("hlibBlendShapeDuplicateTarget")
    def duplicateTarget(self, target, weight_index=None, alias=None, *, fast=False):
        """全ベースのターゲット・in-between・頂点ウェイトを複製する。

        接続は複製せず、現在の形状をベイクする。新しいweight値は0。
        Shape Editorのフォルダ配置と外部ドライバは複製しない。

        Args:
            target (int | str): 元の番号またはエイリアス。
            weight_index (int | None): 未使用の番号。省略時は最小の空き番号。
            alias (str | None): 新しい別名。省略時はMayaのweight表記。
            fast (bool): TrueはOpenMaya直接更新。Undoには記録しない。

        Returns:
            Plug: 新しいターゲットのweight要素。
        """
        index = self._target_index(target)
        destination = self._new_index(weight_index)
        self._check_alias(alias)
        data = self._read_target(index)
        self._write_target(destination, data, alias=alias, value=0.0)
        return self.getPlug("weight")[destination]

    def getTargetVertices(self, target, base=None, full_weight=1.0, *, tolerance=0.0):
        """指定デルタの変位がしきい値を超えるベース頂点だけを取得する。

        現在のweight・envelope・頂点マスクによる変形量ではなく、
        getTargetDeltasが返す絶対デルタの長さで判定する。照会はOpenMayaを使う。

        Args:
            target (int | str): ターゲット番号またはweightのエイリアス。
            base (Node | str | None): ベース。省略時は最小のベース論理番号。
            full_weight (float): 取得する項目のウェイト。in-betweenも指定可能。
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
        deltas = self.getTargetDeltas(target, base=shape, full_weight=full_weight)
        return shape.getVertices(sorted(index for index, delta in deltas.items()
                                        if delta.length() > tolerance))

    @fast_edit
    @undoChunk("hlibBlendShapeReduceTargetDeltas")
    def reduceTargetDeltas(self, target, tolerance=0.0, base=None, full_weight=1.0,
                           disconnect=False, *, fast=False):
        """絶対デルタの長さがしきい値以下の頂点をターゲット項目から除外する。

        格納済みの絶対デルタを判定する。接続中はターゲット形状を自動編集する。
        未接続時は該当頂点の相対補助デルタも除外する。
        weight・envelope・頂点マスクは判定に使用しない。対象がなければ変更しない。

        Args:
            target (int | str): ターゲット番号またはweightのエイリアス。
            tolerance (float): 除外する変位長の上限。有限の非負数。
                通常ターゲットではcm。既定0はゼロデルタのみ除外する。
            base (Node | str | None): ベース。省略時は最小のベース論理番号。
            full_weight (float): 編集する項目のウェイト。in-betweenも指定可能。
            disconnect (bool): 既定Falseは接続先のメッシュを自動編集する。
                Trueなら入力を切断して保存デルタだけを編集する。
            fast (bool): TrueはOpenMaya直接更新。Undoには記録しない。

        Returns:
            BlendShape: 自身。
        """
        if (isinstance(tolerance, bool) or not isinstance(tolerance, (int, float))
                or not math.isfinite(tolerance) or tolerance < 0):
            raise ValueError("tolerance must be a finite nonnegative number")
        deltas = self.getTargetDeltas(target, base=base, full_weight=full_weight)
        vertices = [index for index, delta in deltas.items() if delta.length() <= tolerance]
        return self.resetTargetVertices(target, vertices, base=base, full_weight=full_weight,
                                       disconnect=disconnect)

    @undoChunk("hlibBlendShapeMirrorTarget")
    def mirrorTarget(self, target, axis="X", direction=1, base=None):
        """ターゲットの片側を反対側へミラーする(Maya標準のmirrorTarget)。

        Args:
            target (int | str): 番号またはエイリアス。
            axis (str): オブジェクト空間のX、Y、Z。
            direction (int): Maya標準方向。0=負方向、1=正方向。
            base (Node | str | None): ベース。省略時は先頭。

        Returns:
            BlendShape: 自身。接続中のターゲットは変更せず拒否する。
        """
        bi, index = self._group(target, base)
        self._check_mirror(bi, index, axis)
        if type(direction) is not int or direction not in (0, 1):
            raise ValueError("direction must be 0 or 1")
        cmds.blendShape(self.getName(), edit=True, mirrorTarget=(bi, index),
                        symmetryAxis=axis, symmetrySpace=1, mirrorDirection=direction)
        return self

    @undoChunk("hlibBlendShapeFlipTarget")
    def flipTarget(self, target, axis="X", base=None):
        """左右を交換する。左右別ターゲット作成にはduplicateTarget後に使う。

        Args:
            target (int | str): 番号またはエイリアス。
            axis (str): オブジェクト空間のX、Y、Z。
            base (Node | str | None): ベース。省略時は先頭。

        Returns:
            BlendShape: 自身。接続中のターゲットは変更せず拒否する。
        """
        bi, index = self._group(target, base)
        self._check_mirror(bi, index, axis)
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
        payload = {"format": "hlib.blendShape", "version": 1,
                   "bases": {str(bi): self._topology(self._base_shape(bi)) for bi in self._base_indices()},
                   "baseWeights": {str(bi): self._read_base_weights(bi) for bi in self._base_indices()},
                   "targets": targets,
                   "envelope": self.getPlug("envelope").get(),
                   "origin": self.getPlug("origin").get(),
                   "supportNegativeWeights": self.getPlug("supportNegativeWeights").get()}
        if payload["origin"] == 2:
            raise ValueError("User-defined origin is not supported by dumpTargets")
        destination = os.path.abspath(os.fspath(path))
        fd, temporary = tempfile.mkstemp(prefix=".hlib-blend-", suffix=".json",
                                         dir=os.path.dirname(destination))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
            os.replace(temporary, destination)
        finally:
            if os.path.exists(temporary):
                os.remove(temporary)
        return self

    @fast_edit
    def loadTargets(self, path, *, fast=False):
        """JSONの全ターゲットを空のblendShapeへ復元する。

        先に全データと全ベースの頂点・面接続順を検証する。ベースは保存時と
        同じ論理インデックスで対応させる。既存ターゲットがあれば拒否する。
        既存ノードへの追加ではなく、空のノードへの一式復元用。

        Args:
            path (str | os.PathLike): dumpTargetsで保存したJSON。
            fast (bool): TrueはOpenMaya直接更新。Undoと失敗時の巻き戻しは行わない。

        Returns:
            BlendShape: 自身。通常は1回でUndoでき、失敗時はロールバックする。
                fast=Trueでは変更済みのデータを自動では戻さない。
        """
        with open(path, encoding="utf-8") as stream:
            data = json.load(stream)
        self._validate_file(data)
        if self.getTargetIndices() or self._indices("weight"):
            raise ValueError("loadTargets requires an empty blendShape")
        if not is_fast() and not cmds.undoInfo(query=True, state=True):
            raise RuntimeError("loadTargets requires Maya Undo to be enabled")
        with nullcontext() if is_fast() else undoTransaction("hlibBlendShapeLoadTargets"):
            for key, target in data["targets"].items():
                self._write_target(int(key), target, alias=target["alias"], value=target["value"])
            for attr in ("envelope", "origin", "supportNegativeWeights"):
                self.getPlug(attr).set(data[attr])
            for bi, weights in data["baseWeights"].items():
                for vertex, weight in enumerate(weights):
                    self.getPlug("inputTarget[{}].baseWeights[{}]".format(bi, vertex)).set(weight)
        return self

    @_getter_alias(getTargetAliases)
    def targetAliases(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getTargetAliases(*args, **kwargs)

    @_getter_alias(getWeightPlugs)
    def weightPlugs(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getWeightPlugs(*args, **kwargs)

    @_getter_alias(getWeights)
    def weights(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getWeights(*args, **kwargs)

    @_getter_alias(getGeometry)
    def geometry(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getGeometry(*args, **kwargs)

    @_getter_alias(getTargetIndices)
    def targetIndices(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getTargetIndices(*args, **kwargs)

    @_getter_alias(getTargetPlug)
    def targetPlug(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getTargetPlug(*args, **kwargs)

    @_getter_alias(getInBetweenWeights)
    def inBetweenWeights(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getInBetweenWeights(*args, **kwargs)

    @_getter_alias(getTargetWeights)
    def targetWeights(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getTargetWeights(*args, **kwargs)

    @_getter_alias(getTargetDeltas)
    def targetDeltas(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getTargetDeltas(*args, **kwargs)

    @_getter_alias(getTargetVertices)
    def targetVertices(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getTargetVertices(*args, **kwargs)

    def _remove_live_deltas(self, bi, index, indices, data, source):
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
        shape = self._mesh(Node(target_path))
        self._check_topology(bi, shape)
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
        shape.getVertices(affected).setPositions(positions)

    def _disconnect_target_input(self, path, disconnect):
        """デルタ編集の入力接続ガードを共有し、明示指定時のみ切断する。"""
        destination = self.getPlug(path + ".inputGeomTarget").mplug()
        sources = destination.connectedTo(True, False)
        if sources and not disconnect:
            raise ValueError("Target geometry is connected; use disconnect=True to bake deltas")
        if sources:
            if is_fast():
                self._require_unlocked(destination)
                modifier = om2.MDGModifier()
                modifier.disconnect(sources[0], destination)
                modifier.doIt()
            else:
                cmds.disconnectAttr(sources[0].name(), destination.name())

    def _attr(self, path):
        """内部アトリビュートの完全名を作る。"""
        return self.getName() + "." + path

    def _indices(self, path):
        """配列を確保せず既存の論理番号を取得する。"""
        return sorted(self.getPlug(path).mplug().getExistingArrayAttributeIndices())

    def _base_indices(self):
        """実際に出力ジオメトリを持つベース番号を取得する。"""
        fn = oma2.MFnGeometryFilter(self.mnode())
        return sorted(fn.indexForOutputShape(shape) for shape in fn.getOutputGeometry())

    def _base_shape(self, index):
        """番号に対応するポリゴンベースを取得する。"""
        fn = oma2.MFnGeometryFilter(self.mnode())
        return self._mesh(Node(fn.outputShapeAtIndex(index)))

    def _base_index(self, base):
        """省略または所有ノードからベースの論理番号を解決する。"""
        if base is None:
            indices = self._base_indices()
            if not indices:
                raise ValueError("BlendShape has no base geometry")
            return indices[0]
        shape = self._mesh(base)
        fn = oma2.MFnGeometryFilter(self.mnode())
        for index in self._base_indices():
            if fn.outputShapeAtIndex(index) == shape.mnode():
                return index
        raise ValueError("Geometry is not a base of this blendShape")

    @staticmethod
    def _mesh(value):
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
            node = Node(path)
        if not node.mnode().hasFn(om2.MFn.kMesh):
            raise TypeError("This operation requires polygon mesh geometry")
        return node

    def _target_index(self, target):
        """番号またはweightのエイリアスを解決し存在を確認する。"""
        if type(target) is int:
            index = target
        elif isinstance(target, str):
            matches = [plug.mplug().logicalIndex() for alias, plug in self.getAliases()
                       if alias == target and plug.mplug().isElement
                       and plug.getLongName() == "weight"]
            if not matches:
                raise ValueError("Unknown target alias: " + target)
            index = matches[0]
        else:
            raise TypeError("Target must be an integer index or alias string")
        if index not in self.getTargetIndices():
            raise ValueError("Unknown target index: {}".format(index))
        return index

    def _group(self, target, base):
        """ベースとターゲットの組み合わせを検証する。"""
        bi, index = self._base_index(base), self._target_index(target)
        if index not in self._indices("inputTarget[{}].inputTargetGroup".format(bi)):
            raise ValueError("Target does not exist on this base")
        return bi, index

    @staticmethod
    def _group_path(bi, index):
        """ターゲットグループの相対パスを取得する。"""
        return "inputTarget[{}].inputTargetGroup[{}]".format(bi, index)

    @classmethod
    def _item_path(cls, bi, index, item):
        """ターゲット項目の相対パスを取得する。"""
        return cls._group_path(bi, index) + ".inputTargetItem[{}]".format(item)

    @staticmethod
    def _weight_item(weight):
        """Mayaの0.001刻みの項目番号へ変換し丸め誤差以外を拒否する。"""
        if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not math.isfinite(weight):
            raise ValueError("Weight must be a finite number")
        scaled = weight * 1000.0 + 5000
        if scaled < 0 or scaled > 2147483647 or abs(scaled - round(scaled)) > 1e-6:
            raise ValueError("Weight must be >= -5 and representable in steps of 0.001")
        return int(round(scaled))

    def _item(self, target, base, weight):
        """実在するターゲット項目だけを解決する。"""
        bi, index = self._group(target, base)
        item = self._weight_item(weight)
        if item not in self._indices(self._group_path(bi, index) + ".inputTargetItem"):
            raise ValueError("Target item does not exist at this weight")
        return bi, index, item

    @staticmethod
    def _topology(shape):
        """頂点数と面頂点接続順をJSON互換形式で取得する。"""
        fn = om2.MFnMesh(shape.mnode())
        counts, vertices = fn.getVertices()
        return {"vertices": fn.numVertices, "counts": list(counts), "connects": list(vertices)}

    def _check_topology(self, bi, shape):
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

    def _write_deltas(self, path, values, relative=False):
        """通常はsetAttr、fastではMFnデータとMPlugでデルタを設定する。"""
        prefix = "inputRelative" if relative else "input"
        if is_fast():
            points_plug = self.getPlug(path + "." + prefix + "PointsTarget").mplug()
            components_plug = self.getPlug(path + "." + prefix + "ComponentsTarget").mplug()
            writable(points_plug)
            writable(components_plug)
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
        cmds.setAttr(self._attr(path + "." + prefix + "PointsTarget"), len(values),
                     *[point for _, point in values], type="pointArray")
        cmds.setAttr(self._attr(path + "." + prefix + "ComponentsTarget"), len(values),
                     *["vtx[{}]".format(vertex) for vertex, _ in values], type="componentList")

    def _new_index(self, index):
        """既存weightとターゲットを上書きしない番号を選ぶ。"""
        used = set(self.getTargetIndices()) | set(self._indices("weight"))
        if index is None:
            index = 0
            while index in used:
                index += 1
        if type(index) is not int or not 0 <= index <= 2147483647 or index in used:
            raise ValueError("Expected an unused nonnegative target index")
        return index

    def _check_alias(self, alias):
        """別名の構文と既存アトリビュートとの衝突を検証する。"""
        if alias is not None and (not isinstance(alias, str)
                                  or not re.fullmatch(r"[^\W\d]\w*(?::[^\W\d]\w*)*", alias)
                                  or self.hasAttr(alias)):
            raise ValueError("Alias is invalid or already exists")

    def _check_mirror(self, bi, index, axis):
        """ミラー条件と接続のないデルタであることを確認する。"""
        self._base_shape(bi)
        if axis not in ("X", "Y", "Z"):
            raise ValueError("axis must be X, Y, or Z")
        for item in self._indices(self._group_path(bi, index) + ".inputTargetItem"):
            if self.getPlug(self._item_path(bi, index, item) + ".inputGeomTarget").mplug().isDestination:
                raise ValueError("Mirror requires baked targets; duplicateTarget first")

    def _read_target(self, index):
        """複製と保存に共通のターゲットデータを取得する。"""
        aliases = {plug.mplug().logicalIndex(): alias for alias, plug in self.getAliases()
                   if plug.mplug().isElement and plug.getLongName() == "weight"}
        result = {"alias": aliases.get(index),
                  "value": self.getPlug("weight")[index].get() if index in self._indices("weight") else 0.0,
                  "bases": {}, "inbetweens": {}}
        for bi in self._base_indices():
            group = self._group_path(bi, index)
            if index not in self._indices("inputTarget[{}].inputTargetGroup".format(bi)):
                continue
            if any(self.getPlug(group + "." + attr).get() != 0
                   for attr in ("postDeformersMode", "normalizationId")):
                raise ValueError("Post-deformation and normalization groups are not supported")
            result["bases"][str(bi)] = {
                "weights": self.getTargetWeights(index, self._base_shape(bi)),
                "items": {str(item): self._read_item(bi, index, item) for item in
                          self._indices(group + ".inputTargetItem")}}
        if index in self._indices("inbetweenInfoGroup"):
            root = "inbetweenInfoGroup[{}].inbetweenInfo".format(index)
            for item in self._indices(root):
                path = root + "[{}]".format(item)
                metadata = {attr: self.getPlug(path + "." + attr).get() for attr in
                            ("inbetweenTargetType", "inbetweenTargetName", "interpolation", "inbetweenVisibility")}
                metadata["inbetweenTargetName"] = metadata["inbetweenTargetName"] or "IB"
                metadata["curve"] = {str(i): list(self.getPlug(
                    path + ".interpolationCurve[{}]".format(i)).get())
                    for i in self._indices(path + ".interpolationCurve")}
                result["inbetweens"][str(item)] = metadata
        return result

    def _read_base_weights(self, bi):
        """ベースの頂点マスクを既定値を補って取得する。"""
        count = om2.MFnMesh(self._base_shape(bi).mnode()).numVertices
        path = "inputTarget[{}].baseWeights".format(bi)
        existing = set(self._indices(path))
        array = self.getPlug(path).mplug()
        return [array.elementByLogicalIndex(i).asFloat() if i in existing else 1.0
                for i in range(count)]

    def _write_target(self, index, data, alias, value):
        """検証済みスナップショットを未使用番号へ書き込む。"""
        # setAttrだけで未確保の配列を作ると、Undo後も空のグループが残る。
        # Maya標準のターゲット追加で構造を作り、一時形状を削除してからデルタを復元する。
        for bi, group in data["bases"].items():
            if not is_fast():
                temporary = cmds.duplicate(self._base_shape(int(bi)).getFullName(),
                                           returnRootsOnly=True)[0]
                try:
                    cmds.blendShape(self.getName(), edit=True, target=(
                        self._base_shape(int(bi)).getFullName(), index, temporary, 1.0))
                finally:
                    cmds.delete(temporary)
            for item, payload in group["items"].items():
                path = self._item_path(int(bi), index, int(item))
                self._write_deltas(path, payload["absolute"])
                self._write_deltas(path, payload["relative"], relative=True)
            if not is_fast() and "6000" not in group["items"]:
                cmds.removeMultiInstance(self._attr(self._item_path(int(bi), index, 6000)), b=True)
            path = self._group_path(int(bi), index) + ".targetWeights"
            for vertex, weight in enumerate(group["weights"]):
                if weight != 1.0:
                    self.getPlug(path)[vertex].set(weight)
        for item, metadata in data["inbetweens"].items():
            path = "inbetweenInfoGroup[{}].inbetweenInfo[{}]".format(index, item)
            for attr, metadata_value in metadata.items():
                if attr == "curve":
                    for ci, pair in metadata_value.items():
                        self.getPlug(path + ".interpolationCurve[{}]".format(ci)).set(pair)
                else:
                    self.getPlug(path + "." + attr).set(metadata_value)
        plug = self.getPlug("weight")[index]
        plug.set(value)
        if is_fast():
            # MFnDependencyNodeによる別名更新もUndoキューを使わない。
            fn = om2.MFnDependencyNode(self.mnode())
            name = "weight[{}]".format(index)
            if alias and not fn.setAlias(alias, name, plug.mplug(), True):
                raise RuntimeError("Could not set target alias")
        else:
            plug.setAlias(None)
            if alias:
                plug.setAlias(alias)

    @staticmethod
    def _require_unlocked(plug):
        """入力接続の切断前に所有ノードと親を含むロックを検査する。"""
        if om2.MFnDependencyNode(plug.node()).isLocked:
            raise RuntimeError("Node is locked: " + plug.name())
        current = plug
        while True:
            if current.isLocked:
                raise RuntimeError("Attribute is locked: " + plug.name())
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
            raise RuntimeError("Node is locked: " + destination.name())
        sources = destination.connectedTo(True, False)
        if sources and sources[0] == source:
            raise RuntimeError("Already connected: " + destination.name())
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

    def _validate_file(self, data):
        """ファイル全体を検証し任意のアトリビュート書き込みを防止する。"""
        if not isinstance(data, dict) or data.get("format") != "hlib.blendShape" or data.get("version") != 1:
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
            self._check_alias(alias)
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
