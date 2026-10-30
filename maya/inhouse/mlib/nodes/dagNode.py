"""TransformとShapeに共通するDAG階層へのアクセスを提供する。"""

import maya.api.OpenMaya as om2
import maya.api.OpenMayaAnim as oma2
import maya.cmds as cmds

from ..core.fastWrite import require_writable, set_plug
from ..core.registry import _inherited_node_types, _real_node_type
from ..decorator import _edit_context, _require_bool, undoTransaction
from ..util import _finite_vector, _world_space
from .node import Node

#: 描画のオーバーライドで指定できるカラーインデックスの上限(0〜31)。
_MAX_COLOR_INDEX = 31


def _type_filter(value):
    """getChildren(type=) の指定を型名のtupleへ正規化する。

    Args:
        value (str | Iterable[str] | None): ノード型名、その列、またはNone。

    Returns:
        tuple[str, ...]: 型名。Noneは空。

    Raises:
        TypeError: 文字列・文字列の列・None以外の場合。
        ValueError: 空文字列を含む場合。
    """
    if value is None:
        return ()
    names = (value,) if isinstance(value, str) else tuple(value) if isinstance(value, (list, tuple)) else None
    if names is None or not all(isinstance(name, str) for name in names):
        raise TypeError("type must be a node type name, a sequence of names, or None")
    if not all(names):
        raise ValueError("type must not contain an empty node type name")
    return names


class DagNode(Node):
    """Transform・ShapeのDAGパスを保持し、階層を照会する。

    getParent/getChildrenは保持パス基準。全インスタンスの参照はgetInstancesで取得する。

    各メソッドの「保持するDAGパスが無効」には、保持インスタンスだけが外れた場合に加え、
    ノードごと削除された場合(Undoの記録に残っている間も含む)を含む。その間もMDagPathは
    古いパスを返すため、パスを使う照会は空文字列・削除前の名前を返さずRuntimeErrorにする。
    """

    def getSkinClusters(self):
        """自身のジオメトリを変形するSkinClusterを取得する。

        Shapeは自身、Transformは直下の非中間Shapeを対象にする。
        子Transform以下は検索しない。上流を探索した後、デフォーマの出力Shapeが
        対象と一致するものだけを返すため、別形状の履歴を混入させない。
        Mesh・NURBS等の形状に共通で使用でき、シーンやUndo履歴は変更しない。
        Jointの同名メソッドは従来のinfluence接続照会を維持する。

        Returns:
            list[SkinCluster]: Shape順、各Shapeの上流幅優先順。重複なし。
                対象なしは空リスト。

        Raises:
            RuntimeError: 無効なDAGパス、またはMayaの検索が失敗した場合。
        """
        path = self.mpath()
        obj = path.node()
        if obj.hasFn(om2.MFn.kTransform):
            fn = om2.MFnDagNode(path)
            shapes = [fn.child(i) for i in range(fn.childCount())
                      if fn.child(i).hasFn(om2.MFn.kShape)
                      and not om2.MFnDagNode(fn.child(i)).isIntermediateObject]
        else:
            shapes = [obj] if obj.hasFn(om2.MFn.kShape) else []
        result, seen = [], set()
        for shape in shapes:
            iterator = om2.MItDependencyGraph(
                shape, om2.MFn.kSkinClusterFilter,
                om2.MItDependencyGraph.kUpstream,
                om2.MItDependencyGraph.kBreadthFirst,
                om2.MItDependencyGraph.kNodeLevel,
            )
            iterator.pruningOnFilter = False
            while not iterator.isDone():
                skin = iterator.currentNode()
                key = om2.MFnDependencyNode(skin).uuid().asString()
                if key not in seen and any(
                        output == shape for output in oma2.MFnGeometryFilter(skin).getOutputGeometry()):
                    seen.add(key)
                    result.append(Node(skin))
                iterator.next()
        return result

    def getBindPoses(self):
        """getSkinClusters()で得たSkinClusterのバインドポーズを取得する。

        Shape/Transformは変形対象、Jointは既存のinfluence接続照会を使用する。
        SkinClusterの順を保ち、共有ポーズの重複と未接続を除く。

        Returns:
            list[DagPose]: 接続されたポーズ。対象なしは空リスト。

        Raises:
            RuntimeError: 無効な対象、または不正なバインドポーズ接続。
        """
        result, seen = [], set()
        for skin in self.getSkinClusters():
            pose = skin.getBindPose()
            if pose is not None:
                key = pose.getUuid()
                if key not in seen:
                    seen.add(key)
                    result.append(pose)
        return result

    def mpath(self):
        """保持する可変MDagPathを借用する。コピーは返さない。

        push/pop等で編集する前に ``om2.MDagPath(node.mpath())`` でコピーする。

        Returns:
            om2.MDagPath: 内部で保持するインスタンスのパスと同一のオブジェクト。

        Raises:
            RuntimeError: 保持パスが無効な場合。別インスタンスへ切り替えない。
        """
        dag_path = self._current_dag_path()
        # DagNode は初期化時に必ず DAG パスを解決して保持する(None は非DAGの Node だけ)。
        assert dag_path is not None
        return dag_path

    def mfn(self):
        """保持する DAG パスに対応する function set を、呼び出すたびに新しく作って返す。

        Transform・Mesh 等の派生クラスはさらに具体的な function set へ上書きする。

        Returns:
            om2.MFnDagNode: このインスタンスの function set。

        Raises:
            RuntimeError: 保持する DAG パスが無効な場合。
        """
        return om2.MFnDagNode(self.mpath())

    def getRoot(self):
        """保持するパスの最上位(ワールド直下)の祖先を取得する。

        DAG 上の親は常に Transform なので、Shape から呼んでも戻り値は Transform。
        自身がワールド直下ならその自身を返す。

        Returns:
            DagNode: ワールド直下の祖先、または自身。

        Raises:
            RuntimeError: 保持する DAG パスが無効な場合。
        """
        node = self
        parent = node.getParent()
        while parent is not None:
            node = parent
            parent = node.getParent()
        return node

    def getSiblings(self):
        """同じ親の下にある同じ種類の兄弟を取得する(自身と自身の別インスタンスは含まない)。

        Transform は親直下の他の Transform、Shape は親直下の他の非中間 Shape を DAG の子順で返す。
        自身がワールド直下の Transform なら、他のワールド直下 Transform を対象にする。

        Returns:
            list[DagNode]: 兄弟の参照。無効なノードや兄弟なしは空リスト。

        Raises:
            RuntimeError: ノードは有効だが保持する DAG パスが無効な場合。
        """
        if not self.isValid():
            return []
        is_shape = self._require_mnode().hasFn(om2.MFn.kShape)
        parent = self.getParent()
        if parent is not None:
            candidates = parent._direct_children(is_shape, False, shapes_only=is_shape)
        elif is_shape:
            candidates = []
        else:
            candidates = DagNode._world_assemblies()
        self_uuid = self.getUuid()
        return [candidate for candidate in candidates if candidate.getUuid() != self_uuid]

    def getBoundingBox(self, worldSpace=False):
        """バウンディングボックスを取得する。

        ``MFnDagNode.boundingBox`` は自身の translate/rotate/scale(Transform の場合)は含むが、
        親から継承した変換は含まない(``cmds.xform(-boundingBox)`` と同じ)。
        ``worldSpace=True`` はそこへ保持パスの ``exclusiveMatrix`` (親までのワールドマトリクス)を
        適用し、ワールド空間のボックスを返す。Shape では自身のローカル形状から計算する。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseは親の変換を含まない空間。既定False。

        Returns:
            om2.MBoundingBox: 軸並行境界ボックス。Maya API の内部距離単位。
                子 Shape が無い Transform では原点のみを含む空に近いボックスになる。

        Raises:
            ValueError: worldSpaceが bool でない場合。
            RuntimeError: ノードが無効、または保持する DAG パスが無効な場合。
        """
        world = _world_space(worldSpace)
        self._require_valid("compute the bounding box of")
        path = self.mpath()
        box = om2.MFnDagNode(path).boundingBox
        if not world:
            return box
        parent_matrix = path.exclusiveMatrix()
        world_box = om2.MBoundingBox()
        for x in (box.min.x, box.max.x):
            for y in (box.min.y, box.max.y):
                for z in (box.min.z, box.max.z):
                    world_box.expand(om2.MPoint(x, y, z) * parent_matrix)
        return world_box

    def isIntermediateObject(self):
        """中間オブジェクト(履歴用の非表示 Shape)か判定する。Transform では常に False。

        Returns:
            bool: 中間オブジェクトの場合は True。

        Raises:
            RuntimeError: 保持する DAG パスが無効な場合。
        """
        return self.mfn().isIntermediateObject

    def getInstances(self, noSelf=False):
        """同じDAGノードの全インスタンスを、複製せず参照する。

        Args:
            noSelf (bool): Trueなら保持するパスを除外する。既定False。

        Returns:
            list[DagNode]: 間接インスタンスも含むAPI列挙順の参照。
                保持パスは自身、それ以外は新しいラッパー。インスタンスは追加しない。

        Raises:
            RuntimeError: 保持するDAGパスが無効な場合。
        """
        original = self.mpath().fullPathName()
        # APIが列挙した有効なパスの複製なので、Node(...) の入力解決を省いて同じ型で包む。
        return [self if path.fullPathName() == original else Node._wrap_dag_path(om2.MDagPath(path))
                for path in om2.MDagPath.getAllPathsTo(self.mnode())
                if not noSelf or path.fullPathName() != original]

    def getParents(self, indirect=False):
        """直接の親をノード単位またはパス単位で取得する。祖先全体ではない。

        Args:
            indirect (bool): FalseはAPIの親ノード順。保持パスの親にはそのパスを使い、
                他の親はAPIで得た一つのパスを使う。
                TrueはgetInstances順に各パスの親を返し、親のインスタンス化による別パスも含む。

        Returns:
            list[DagNode]: 重複統合しない親の参照。保持パスがワールド直下なら空リスト。

        Raises:
            RuntimeError: 保持するDAGパスが無効な場合。
        """
        parent = self.getParent()
        if parent is None:
            return []
        if indirect:
            return [instance.getParent() for instance in self.getInstances() if instance.getParent() is not None]
        fn = self.mfn()
        return [parent if fn.parent(index) == parent.mnode()
                else Node._wrap_dag_path(om2.MDagPath.getAPathTo(fn.parent(index)))
                for index in range(fn.parentCount())
                if not fn.parent(index).hasFn(om2.MFn.kWorld)]

    def getParent(self, step=1):
        """保持パスを指定階層だけ遡る。

        Args:
            step (int): 遡る階層数。0以下、またはワールドまで遡る場合はNone。

        Returns:
            DagNode | None: 遡ったパスの新しいラッパー。親がない場合はNone。

        Raises:
            RuntimeError: 正のstepで取得する際、保持するDAGパスが無効な場合。
        """
        if step <= 0:
            return None
        path = om2.MDagPath(self.mpath())
        if step >= path.length():
            return None
        path.pop(step)
        # 有効な保持パスの複製を遡ったパスなので、Node(path) の入力解決を省いて同じ型で包む。
        return Node._wrap_dag_path(path)

    def getChildren(self, shapes=False, intermediates=False, *, allDescendents=False,
                    order="depthFirst", leaves=False, includeSelf=False, underWorld=False, type=None):
        """保持パスに沿って子・子孫を列挙する。同じノードの別パスも残す。

        子パスを継ぎ足して探索し、名前から再解決しない。

        Args:
            type (str | Iterable[str] | None): Mayaのノード型で結果を絞る(``cmds.listRelatives(type=)``
                と同じく派生型を含む。:meth:`~mlib.nodes.node.Node.isType` で判定)。探索自体は絞らないため、
                ``allDescendents=True`` では型の違う子の下も探す。Shapeの型(``"mesh"`` 等)を指定した場合は
                shapes=Falseでも Shape を含めて探す。``multDoubleLinear``/``multDL`` のような版の互換名も使える。
            shapes (bool): Shapeも含める。既定はTransformのみ。
            intermediates (bool): 中間オブジェクトを含める。除外した子の下は探索しない。
            allDescendents (bool): Trueは子孫全体、Falseは直接の子だけ。
            order (str): depthFirstまたはbreadthFirst。兄弟間はDAGの子順。
            leaves (bool): 探索対象の子TransformがないTransformを再帰取得する。Shapeの有無は問わない。
                shapes=Trueとは併用不可。
            includeSelf (bool): 自身もshapes/leaves条件で判定し、該当すれば同じラッパーを返す。
            underWorld (bool): Shape下のアンダーワールドも探索する。

        Returns:
            list[DagNode]: 探索順の参照。対象なし、またはノード自体が無効なら空リスト。

        Raises:
            TypeError: allDescendents・leaves・includeSelf・underWorldがboolでない、またはtypeが
                文字列・文字列の列・None以外の場合。
            ValueError: 探索順が不正、leavesとshapesを併用した、またはtypeが空文字列の場合。
            RuntimeError: ノードは有効だが保持するDAGパスが無効な場合。
        """
        for value, name in ((allDescendents, "allDescendents"), (leaves, "leaves"),
                            (includeSelf, "includeSelf"), (underWorld, "underWorld")):
            _require_bool(value, name)
        if order not in ("depthFirst", "breadthFirst"):
            raise ValueError("order must be 'depthFirst' or 'breadthFirst'")
        if leaves and shapes:
            raise ValueError("leaves selects transforms and cannot be combined with shapes")
        types = _type_filter(type)
        if types and not leaves and not shapes:
            # Shapeの型で絞る場合は、既定のTransformだけの探索では必ず空になるためShapeも探す。
            shapes = any("shape" in _inherited_node_types(_real_node_type(name)) for name in types)
        if not self.isValid():
            return []
        result = self._collect_children(shapes, intermediates, allDescendents, order, leaves, includeSelf, underWorld)
        if types:
            result = [node for node in result if any(node.isType(name) for name in types)]
        return result

    def getShape(self, index=0, intermediates=False):
        """保持パスに対応する Shape を取得する。

        契約: 自身が Shape なら ``index``・``intermediates`` を無視して自身を返す。Transform は
        派生クラス(Transform.getShape)が直下の Shape を ``index`` 番目(0 始まり。範囲外は None)で返す。
        それ以外の DAG ノードは None。無効な index で IndexError にはしない。

        Args:
            index (int): Transform で選ぶ Shape の番号。Shape では無視する。既定 0。
            intermediates (bool): Transform で中間オブジェクトも候補に含める。Shape では無視する。

        Returns:
            DagNode | None: Shape なら自身、Transform は選んだ Shape、該当なしは None。

        Raises:
            RuntimeError: ノードが破棄されている場合。
        """
        return self if self._require_mnode().hasFn(om2.MFn.kShape) else None

    def isVisible(self):
        """親階層を含むDAGの表示状態。

        Returns:
            bool: 親階層を含むDAGの表示状態。

        Raises:
            RuntimeError: 保持するDAGパスが無効な場合(削除済みのノードを含む)。
        """
        return self.mpath().isVisible()

    def show(self, *, fast=False):
        """visibility を有効にして自身を返す。``setVisibility(True, fast=fast)`` と同じ。

        Args:
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            DagNode: 自身。

        Raises:
            TypeError: fastがbool以外の場合。
        """
        return self.setVisibility(True, fast=fast)

    def hide(self, *, fast=False):
        """visibility を無効にして自身を返す。``setVisibility(False, fast=fast)`` と同じ。

        Args:
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            DagNode: 自身。

        Raises:
            TypeError: fastがbool以外の場合。
        """
        return self.setVisibility(False, fast=fast)

    def getColor(self):
        """描画のオーバーライドの表示色を取得する。

        Transformは直下の最初の中間でないShape、Shapeが無ければ自身を読む(:meth:`setColor` と同じ対象)。

        Returns:
            int | tuple[float, float, float] | None: ``overrideEnabled`` が無効ならNone。
                ``overrideRGBColors`` が有効なら (r, g, b)、それ以外はカラーインデックス(0は既定色)。

        Raises:
            RuntimeError: ノードが無効な場合。
        """
        fn = om2.MFnDependencyNode(self._color_targets()[0]._require_mnode())
        if not fn.findPlug("overrideEnabled", False).asBool():
            return None
        if fn.findPlug("overrideRGBColors", False).asBool():
            plug = fn.findPlug("overrideColorRGB", False)
            return tuple(plug.child(index).asFloat() for index in range(3))
        return fn.findPlug("overrideColor", False).asInt()

    def setColor(self, color, *, fast=False):
        """描画のオーバーライドで表示色を設定し、自身を返す。

        ``overrideEnabled`` を有効にし、インデックス指定は ``overrideRGBColors`` を無効にして
        ``overrideColor``、RGB指定は ``overrideRGBColors`` を有効にして ``overrideColorRGB`` を設定する。
        Transformは直下の中間でないShapeへ設定し、Shapeが無いTransform(グループ・Joint等)は自身へ
        設定する(:meth:`getColor` も同じ対象を読む)。通常は ``cmds.setAttr`` で1回のUndoにまとめ、途中で
        失敗した場合は巻き戻す。``fast=True`` は全対象アトリビュートの書込み可否を先に調べてから
        OpenMayaで書き込み、Undoに記録しない。

        Args:
            color (int | Sequence[float]): カラーインデックス(0〜31。0は既定色)、または
                0〜1の有限な数値3個の (r, g, b)。RGBは表示色の値で、色空間の変換は行わない。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            DagNode: 自身。

        Raises:
            TypeError: colorがint・3個の数値の列以外(boolを含む)、またはfastがbool以外の場合。
            ValueError: インデックスが0〜31の範囲外、またはRGBの成分数が3でない・0〜1の範囲外の場合。
            RuntimeError: ノードが無効、またはロック・入力接続でMayaが設定を拒否した場合。
        """
        _require_bool(fast, "fast")
        index, rgb = _color_value(color)
        if fast:
            self._set_color_fast(index, rgb)
            return self
        targets = [target.getFullName() for target in self._color_targets()]
        with undoTransaction("mlibDagNodeSetColor"):
            for name in targets:
                cmds.setAttr(name + ".overrideEnabled", True)
                if rgb is None:
                    cmds.setAttr(name + ".overrideRGBColors", False)
                    cmds.setAttr(name + ".overrideColor", index)
                else:
                    cmds.setAttr(name + ".overrideRGBColors", True)
                    cmds.setAttr(name + ".overrideColorRGB", *rgb)
        return self

    def getVisibility(self):
        """自身のvisibilityアトリビュート値。親や表示レイヤーを含む最終可視性ではない。

        Returns:
            bool: 自身のvisibilityアトリビュート値。親や表示レイヤーを含む最終可視性ではない。
        """
        return bool(self.getPlug("visibility").get())

    def setVisibility(self, state, *, fast=False):
        """visibility を指定した状態に設定する。親やレイヤーの可視性は変更しない。

        Args:
            state (bool): visibilityへ設定する値。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            DagNode: 自身。

        Note:
            ``fast=True`` はOpenMaya直接更新(Undoなし)。既定の ``False`` は通常処理。
            fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        with _edit_context("mlibDagNodeSetVisibility", fast):
            _require_bool(state, "state")
            self.getPlug("visibility").set(state, fast=fast)
            return self

    def getOutlinerVisibility(self):
        """アウトライナーでの表示を許可する設定値を取得する。

        Returns:
            bool: hiddenInOutlinerがFalseならTrue。実際の画面上の可視性ではない。

        Raises:
            AttributeError: hiddenInOutlinerがないノードの場合。
            RuntimeError: ノードが無効な場合。

        Note:
            エディターのフィルター・親の折り畳み・非表示ノード表示設定は判定しない。
        """
        return not bool(self.getPlug("hiddenInOutliner").get())

    def setOutlinerVisibility(self, state, *, fast=False):
        """ノードのアウトライナー表示を切り替える。

        Args:
            state (bool): Trueで表示、Falseで非表示(hiddenInOutlinerを反転設定)。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            DagNode: 自身。DagNodes・Transforms・Jointsからの一括操作にも対応する。

        Raises:
            TypeError: stateまたはfastがbool以外の場合。
            AttributeError: 対応アトリビュートがない場合。
            RuntimeError: ロック・入力接続などで更新できない場合。

        Note:
            ビューポートのvisibilityは変更しない。表示の最終結果は各Outlinerの
            フィルターや非表示ノード表示設定にも依存する。
        """
        with _edit_context("mlibDagNodeSetOutlinerVisibility", fast):
            _require_bool(state, "state")
            self.getPlug("hiddenInOutliner").set(not state, fast=fast)
            return self

    def _collect_children(self, shapes, intermediates, all_descendents, order, leaves, include_self, under_world):
        """検証済みの条件で子・子孫を探索する(:meth:`getChildren` の本体)。

        Args:
            shapes (bool): Shapeも含める。
            intermediates (bool): 中間オブジェクトを含める。
            all_descendents (bool): 子孫全体を探す。
            order (str): depthFirstまたはbreadthFirst。
            leaves (bool): 子Transformを持たないTransformだけを返す。
            include_self (bool): 自身も判定する。
            under_world (bool): アンダーワールドも探す。

        Returns:
            list[DagNode]: 探索順の参照。
        """
        recursive = all_descendents or leaves
        from collections import deque
        pending = deque([(self, 0)])
        result = []
        while pending:
            node, depth = pending.popleft() if order == "breadthFirst" else pending.pop()
            is_shape = node._require_mnode().hasFn(om2.MFn.kShape)
            children = node._traversal_children(shapes, intermediates, under_world) if recursive or depth == 0 else []
            selected = (include_self or depth > 0) and (shapes or not is_shape)
            if selected and (not leaves or not any(
                    child.mnode().hasFn(om2.MFn.kTransform) for child in children)):
                result.append(node)
            if recursive or depth == 0:
                rows = [(child, depth + 1) for child in children]
                pending.extend(rows if order == "breadthFirst" else reversed(rows))
        return result

    def _set_color_fast(self, index, rgb):
        """:meth:`setColor` の値をOpenMayaで書き込む。Undoには記録しない。

        一部の対象だけ色が変わるのを避けるため、全アトリビュート(コンパウンドアトリビュートは子も)の
        書込み可否を先に調べてから書き込む。

        Args:
            index (int | None): カラーインデックス。RGB指定ではNone。
            rgb (tuple[float, float, float] | None): RGB。インデックス指定ではNone。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: ノードが無効、またはロック・入力接続で書き込めない場合。
        """
        writes = []
        for target in self._color_targets():
            # Plugラッパーを作らず、組み込みアトリビュートのMPlugを直接取る。
            fn = target._dependency_fn()
            plugs = {name: fn.findPlug(name, False) for name in
                     ("overrideEnabled", "overrideRGBColors", "overrideColor", "overrideColorRGB")}
            writes += [(plugs["overrideEnabled"], True), (plugs["overrideRGBColors"], rgb is not None)]
            writes.append((plugs["overrideColor"], index) if rgb is None else (plugs["overrideColorRGB"], rgb))
        for plug, _ in writes:
            require_writable(plug)
            for child in range(plug.numChildren() if plug.isCompound else 0):
                require_writable(plug.child(child))
        for plug, value in writes:
            set_plug(plug, value, _writable_checked=True)

    def _color_targets(self):
        """:meth:`setColor`・:meth:`getColor` の対象を返す。DagNodeは自身。

        Returns:
            list[DagNode]: 表示色を設定するノード。
        """
        self._require_valid("set the color of")
        return [self]

    def _require_mnode(self):
        """保持する MObject を返す。:meth:`mnode` と同じ値で、None にならないことを確かめる。

        初期化でノードを解決できなければ例外になるため、生成済みのラッパーは常に MObject を保持する。

        Returns:
            om2.MObject: 保持している MObject(複製ではない)。
        """
        mobject = self.mnode()
        assert mobject is not None
        return mobject

    @staticmethod
    def _world_assemblies():
        """ワールド直下の Transform をすべて取得する。

        Returns:
            list[DagNode]: ワールド直下(DAG パスの長さが 1)の Transform ラッパー。
        """
        iterator = om2.MItDag(om2.MItDag.kBreadthFirst, om2.MFn.kTransform)
        assemblies = []
        while not iterator.isDone():
            path = iterator.getPath()
            if path.length() == 1:
                # MItDag が返した有効なパスなので、Node(path) の入力解決を省いて同じ型で包む。
                assemblies.append(Node._wrap_dag_path(path))
            iterator.next()
        return assemblies

    def _direct_children(self, shapes, intermediates, shapes_only=False):
        """直接の子をAPIで列挙し、インスタンスの親パスを維持する。

        Args:
            shapes (bool): Shapeも列挙するか。
            intermediates (bool): 中間オブジェクトも含めるか。
            shapes_only (bool): TrueならShapeだけを列挙する(Transform等はラッパーを作らずに除く)。

        Returns:
            list[DagNode]: 条件に合う直接の子。非Transformでは空リスト。
        """
        path = self.mpath()
        if not path.node().hasFn(om2.MFn.kTransform):
            return []
        # 子の数と子は保持パスから直接読む(MFnDagNode(path) と同じ子の順。関数セットの作成を省く)。
        result = []
        for index in range(path.childCount()):
            obj = path.child(index)
            if not shapes and not obj.hasFn(om2.MFn.kTransform):
                continue
            if shapes_only and not obj.hasFn(om2.MFn.kShape):
                continue
            if not intermediates and om2.MFnDagNode(obj).isIntermediateObject:
                continue
            child = om2.MDagPath(path)
            child.push(obj)
            # 直前に延長した有効なパスなので、Node(child)の入力解決を省いて同じ型で包む。
            result.append(Node._wrap_dag_path(child))
        return result

    def _traversal_children(self, shapes, intermediates, under_world):
        """指定条件で探索を続ける子パスを取得する。

        Args:
            shapes: TrueはShapeも取得対象へ含める。
            intermediates: Trueは中間オブジェクトも含める。
            under_world: TrueはShape下のアンダーワールドも探索する。
        """
        result = []
        is_shape = self._require_mnode().hasFn(om2.MFn.kShape)
        if under_world and (is_shape or not shapes):
            shape = self if is_shape else self.getShape()
            if shape is not None:
                iterator = om2.MItDag()
                iterator.reset(shape.mpath())
                iterator.traverseUnderWorld = True
                iterator.next()
                if not iterator.isDone():
                    root = iterator.getPath()
                    # アンダーワールドの非表示ルート自体は公開せず、その子を探索する。
                    if not om2.MFnDagNode(root).inModel:
                        for index in range(root.childCount()):
                            path = om2.MDagPath(root)
                            path.push(root.child(index))
                            if intermediates or not om2.MFnDagNode(path).isIntermediateObject:
                                result.append(Node._wrap_dag_path(path))
        result.extend(self._direct_children(shapes, intermediates))
        return result


def _color_value(color):
    """setColorの色指定を検証する。

    Args:
        color (int | Sequence[float]): カラーインデックス、または (r, g, b)。

    Returns:
        tuple[int | None, tuple[float, float, float] | None]: インデックス指定なら (番号, None)、
            RGB指定なら (None, (r, g, b))。

    Raises:
        TypeError: 型が不正な場合。
        ValueError: 範囲・成分数が不正な場合。
    """
    if isinstance(color, bool):
        raise TypeError("color must be an int index or an (r, g, b) sequence, not bool")
    if isinstance(color, int):
        if not 0 <= color <= _MAX_COLOR_INDEX:
            raise ValueError(f"color index must be between 0 and {_MAX_COLOR_INDEX}, got {color}")
        return color, None
    if isinstance(color, (str, bytes)) or not hasattr(color, "__iter__"):
        raise TypeError("color must be an int index or an (r, g, b) sequence")
    rgb = _finite_vector(color, 3, "color")
    if not all(0.0 <= value <= 1.0 for value in rgb):
        raise ValueError("color RGB components must be between 0 and 1")
    return None, rgb
