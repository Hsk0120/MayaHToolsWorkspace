"""TransformとShapeに共通するDAG階層へのアクセスを提供する。"""

import inspect

import maya.api.OpenMaya as om2
import maya.api.OpenMayaAnim as oma2
import maya.cmds as cmds

from .._core.flags import flag_aliases
from .._core.getterAlias import _getter_alias
from ..common._fast import fast_edit
from ..decorator import undoChunk
from .node import Node, Nodes


class DagNode(Node):
    """DAGノードの共通基底。具象ラッパーの型登録は変更しない。"""

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
        """保持するインスタンスのDAGパスを取得する。

        Returns:
            om2.MDagPath: この参照が保持するDAGパス。

        Raises:
            RuntimeError: 保持していたパスが無効な場合。他のインスタンスへ切り替えない。
        """
        return self._current_dag_path()

    def getInstances(self, noSelf=False):
        """同じDAGノードの各インスタンスを取得する。

        Args:
            noSelf (bool): 現在のパスを除外する。
        Returns:
            list[DagNode]: 間接インスタンスを含むパスごとのノード参照。
        """
        original = self.mpath().fullPathName()
        return [self if path.fullPathName() == original else Node(om2.MDagPath(path))
                for path in om2.MDagPath.getAllPathsTo(self.mnode())
                if not noSelf or path.fullPathName() != original]

    def getParents(self, indirect=False):
        """直接の親をインスタンスごとに取得する。

        Args:
            indirect (bool): 間接インスタンスを含む全ての親パスを返す。
        Returns:
            list[DagNode]: 直接の親。ルートでは空リスト。
        """
        parent = self.getParent()
        if parent is None:
            return []
        if indirect:
            return [instance.getParent() for instance in self.getInstances() if instance.getParent() is not None]
        fn = self.dagFn()
        return [parent if fn.parent(index) == parent.mnode()
                else Node(om2.MDagPath.getAPathTo(fn.parent(index)))
                for index in range(fn.parentCount())
                if not fn.parent(index).hasFn(om2.MFn.kWorld)]

    def iterBreadthFirst(self, shapes=False, intermediates=False, underWorld=False):
        """自身からDAGを幅優先で反復する。

        Args:
            shapes (bool): Shapeを含める。
            intermediates (bool): 中間オブジェクトを含める。
            underWorld (bool): Shape下のアンダーワールドを探索する。
        Yields:
            DagNode: インスタンスのパスを保持したノード。
        """
        from collections import deque
        queue = deque([self])
        while queue:
            node = queue.popleft()
            is_shape = node.mnode().hasFn(om2.MFn.kShape)
            if shapes or not is_shape:
                yield node
            queue.extend(node._traversal_children(shapes, intermediates, underWorld))

    def iterDepthFirst(self, shapes=False, intermediates=False, underWorld=False):
        """自身からDAGを深さ優先で反復する。

        Args:
            shapes (bool): Shapeを含める。
            intermediates (bool): 中間オブジェクトを含める。
            underWorld (bool): アンダーワールドを探索する。
        Yields:
            DagNode: パスを保持したノード。
        """
        stack = [self]
        while stack:
            node = stack.pop()
            if shapes or not node.mnode().hasFn(om2.MFn.kShape):
                yield node
            stack.extend(reversed(node._traversal_children(shapes, intermediates, underWorld)))

    def dagFn(self):
        """保持するDAGパスに対応するfunction setを取得する。

        Returns:
            om2.MFnDagNode: このインスタンスのfunction set。

        Raises:
            RuntimeError: 保持していたパスが無効な場合。
        """
        return om2.MFnDagNode(self.mpath())

    def getParentPath(self):
        """保持するインスタンスの親パスを取得する。

        Returns:
            om2.MDagPath | None: 親のパス。無効なノード、またはルートならNone。

        Raises:
            RuntimeError: ノードは存在するが保持していたパスが無効な場合。
        """
        if not self.isValid():
            return None
        path = self.mpath()
        if path.length() <= 1:
            return None
        parent = om2.MDagPath(path)
        parent.pop()
        return parent

    def getParent(self, step=1):
        """親ノードを登録された型の Node として取得する。

        Args:
            step (int): 遡る階層数。0以下またはルートを越える場合はNone。
        Returns:
            Node | None: 親ノード。親がない場合は ``None``。
        """
        if step <= 0:
            return None
        path = om2.MDagPath(self.mpath())
        if step >= path.length():
            return None
        path.pop(step)
        return Node(path)

    def getFullPath(self):
        """保持するDAGインスタンスの完全パス。

        Returns:
            str: 保持するDAGインスタンスの完全パス。
        """
        return self.mpath().fullPathName()

    def getChildren(self, shapes=False, intermediates=False):
        """非TransformのDAGノードでは空の子リストを返す。

        Args:
            shapes (bool): Transform側のShape取得指定。
            intermediates (bool): Transform側の中間ノード取得指定。
        Returns:
            list: 空リスト。Transformではオーバーライドする。
        """
        return []

    @flag_aliases(index="idx")
    def getShape(self, idx=0, intermediates=False):
        """Shape自身を返す。Transformでは指定Shapeを取得する。

        Args:
            idx (int): Shape自身では無視する。 別名 ``index`` も使用可能。
            intermediates (bool): Shape自身では無視する。
        Returns:
            DagNode | None: Shapeなら自身、それ以外はNone。
        """
        return self if self.mnode().hasFn(om2.MFn.kShape) else None

    def getPartialPath(self):
        """保持するDAGインスタンスの最短一意パス。

        Returns:
            str: 保持するDAGインスタンスの最短一意パス。
        """
        return self.mpath().partialPathName()

    def isVisible(self):
        """親階層を含むDAGの表示状態。

        Returns:
            bool: 親階層を含むDAGの表示状態。
        """
        return self.mpath().isVisible()

    def show(self):
        """visibilityを有効にして自身を返す。

        Returns:
            DagNode: visibilityを有効にして自身を返す。
        """
        return self.setVisibility(True)

    def hide(self):
        """visibilityを無効にして自身を返す。

        Returns:
            DagNode: visibilityを無効にして自身を返す。
        """
        return self.setVisibility(False)

    def getVisibility(self):
        """自身のvisibilityアトリビュート値。親や表示レイヤーを含む最終可視性ではない。

        Returns:
            bool: 自身のvisibilityアトリビュート値。親や表示レイヤーを含む最終可視性ではない。
        """
        return bool(self.getPlug("visibility").get())

    @fast_edit
    @undoChunk("hlibNodeSetVisible")
    def setVisibility(self, state, *, fast=False):
        """visibility を指定した状態に設定する。親やレイヤーの可視性は変更しない。

        Args:
            state (bool): visibilityへ設定する値。
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。

        Returns:
            DagNode: 自身。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        if not isinstance(state, bool):
            raise TypeError("state must be a bool")
        self.getPlug("visibility").set(state)
        return self

    def getOutlinerVisibility(self):
        """アウトライナーでの表示を許可する設定値を取得する。

        Returns:
            bool: hiddenInOutlinerがFalseならTrue。実際の画面上の可視性ではない。

        Raises:
            AttributeError: hiddenInOutlinerがないノードの場合。
            RuntimeError: ノードが無効な場合。

        エディターのフィルター・親の折り畳み・非表示ノード表示設定は判定しない。
        """
        return not bool(self.getPlug("hiddenInOutliner").get())

    @fast_edit
    @undoChunk("hlibNodeSetOutlinerVisibility")
    def setOutlinerVisibility(self, state, *, fast=False):
        """ノードのアウトライナー表示を切り替える。

        Args:
            state (bool): Trueで表示、Falseで非表示（hiddenInOutlinerを反転設定）。
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。

        Returns:
            DagNode: 自身。DagNodes・Transforms・Jointsからの一括操作にも対応する。

        Raises:
            TypeError: stateまたはfastがboolでない場合。
            AttributeError: 対応アトリビュートがない場合。
            RuntimeError: ロック・入力接続などで更新できない場合。

        ビューポートのvisibilityは変更しない。表示の最終結果は各Outlinerの
        フィルターや非表示ノード表示設定にも依存する。
        """
        if not isinstance(state, bool):
            raise TypeError("state must be a bool")
        self.getPlug("hiddenInOutliner").set(not state)
        return self

    def getOutlinerColor(self):
        """このノードのOutliner色。無効時はdisabledモード。

        Returns:
            Color: このノードのOutliner色。無効時はdisabledモード。
        """
        from ..common.color import Color
        if not self.getPlug("useOutlinerColor").get():
            return Color.disabled()
        return Color(rgb=self.getPlug("outlinerColor").get())

    @fast_edit
    @undoChunk("hlibNodeOutlinerColor")
    def setOutlinerColor(self, color, *, fast=False):
        """このノードのOutliner色を設定する。色番号は保持RGBへ変換する。

        Args:
            color (Color | int | Iterable[float] | None): 表示色。None/disabledは無効化。
            fast (bool): TrueはOpenMaya直接更新でUndoなし。
        Returns:
            DagNode: 自身。入力Colorの変更は自動反映しない。
        Raises:
            ValueError: 色の値が不正な場合。
            RuntimeError: アトリビュートがない、ロック・接続済みなど変更できない場合。
        """
        from ..common.color import Color
        value = Color.coerce(color)
        self._set_display_color(self._display_color_updates(value, outliner=True))
        return self

    def getOverrideColor(self):
        """Color: 自身のDrawing Overrides色。最終表示色ではない。

        親・表示レイヤー・選択ハイライトは合成しない。
        アトリビュートがない場合はRuntimeError。無効時はdisabledモードを返す。
        """
        from ..common.color import Color
        if not self.getPlug("overrideEnabled").get():
            return Color.disabled()
        if self.getPlug("overrideRGBColors").get():
            return Color(rgb=self.getPlug("overrideColorRGB").get())
        return Color(index=self.getPlug("overrideColor").get())

    @fast_edit
    @undoChunk("hlibNodeOverrideColor")
    def setOverrideColor(self, color, *, fast=False):
        """指定形式のままDrawing Overrides色を設定する。子Shapeへは転送しない。

        Args:
            color (Color | int | Iterable[float] | None): 0～31の番号、0～1のRGB、
                または表示色オブジェクト。None/disabledはoverrideEnabled全体を
                無効化するため、表示タイプ等にも影響する。
            fast (bool): TrueはOpenMaya直接更新でUndoなし。
        Returns:
            DagNode: 自身。RGBモードは近似番号ではなく元のRGBを適用する。
        Raises:
            ValueError: 色の値が不正な場合。
            RuntimeError: アトリビュートがない、ロック・接続済みなど変更できない場合。
        """
        from ..common.color import Color
        value = Color.coerce(color)
        self._set_display_color(self._display_color_updates(value))
        return self

    @_getter_alias(getSkinClusters)
    def skinClusters(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getSkinClusters(*args, **kwargs)

    @_getter_alias(getBindPoses)
    def bindPoses(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getBindPoses(*args, **kwargs)

    @_getter_alias(getInstances)
    def instances(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getInstances(*args, **kwargs)

    @_getter_alias(getParents)
    def parents(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getParents(*args, **kwargs)

    @_getter_alias(getParentPath)
    def parentPath(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getParentPath(*args, **kwargs)

    @_getter_alias(getParent)
    def parent(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getParent(*args, **kwargs)

    @_getter_alias(getFullPath)
    def fullPath(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getFullPath(*args, **kwargs)

    @_getter_alias(getChildren)
    def children(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getChildren(*args, **kwargs)

    @_getter_alias(getShape)
    def shape(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getShape(*args, **kwargs)

    @_getter_alias(getPartialPath)
    def partialPath(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getPartialPath(*args, **kwargs)

    @_getter_alias(getVisibility)
    def visibility(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getVisibility(*args, **kwargs)

    @_getter_alias(getOutlinerVisibility)
    def outlinerVisibility(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getOutlinerVisibility(*args, **kwargs)

    @_getter_alias(getOutlinerColor)
    def outlinerColor(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getOutlinerColor(*args, **kwargs)

    @_getter_alias(getOverrideColor)
    def overrideColor(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getOverrideColor(*args, **kwargs)

    def _traversal_children(self, shapes, intermediates, under_world):
        """指定条件で探索を続ける子パスを取得する。

        Args:
            shapes: TrueはShapeも取得対象へ含める。
            intermediates: Trueは中間オブジェクトも含める。
            under_world: TrueはShape下のアンダーワールドも探索する。
        """
        result = []
        is_shape = self.mnode().hasFn(om2.MFn.kShape)
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
                                result.append(Node(path))
        result.extend(self.getChildren(shapes=shapes, intermediates=intermediates))
        return result

    @staticmethod
    def _display_color_updates(value, outliner=False):
        """正規化済みColorから対象アトリビュートと値の更新計画を作る。

        Args:
            value: 変換・設定する入力値。
            outliner: TrueはOutliner色、FalseはDrawing Overridesを扱う。
        """
        if outliner:
            updates = [] if value.mode == "disabled" else [("outlinerColor", value.rgb)]
            return updates + [("useOutlinerColor", value.mode != "disabled")]
        updates = []
        if value.mode == "index":
            updates = [("overrideColor", value.index), ("overrideRGBColors", False)]
        elif value.mode == "rgb":
            updates = [("overrideColorRGB", value.rgb), ("overrideRGBColors", True)]
        return updates + [("overrideEnabled", value.mode != "disabled")]

    def _prepare_display_color(self, updates):
        """全アトリビュートの存在・書込み可否を検証してPlugと値の計画を返す。

        Args:
            updates: アトリビュートと設定値の更新計画。
        """
        if not self.isValid():
            raise RuntimeError("Cannot color an invalid node")
        if om2.MFnDependencyNode(self.mnode()).isLocked:
            raise RuntimeError("Cannot color a locked node: " + self.getFullName())
        if any(not cmds.objExists(self.getFullName() + "." + name) for name, _ in updates):
            raise RuntimeError("Node does not have the requested display color attributes")
        plugs = [(self.getPlug(name), value) for name, value in updates]
        for plug, value in plugs:
            plug._require_writable()
        return plugs

    @staticmethod
    def _apply_display_color(plugs):
        """検証済みの計画を現在のfastモードで適用する。実行時失敗は伝播する。

        Args:
            plugs: 照会または更新するアトリビュート参照。
        """
        for plug, value in plugs:
            plug.set(value)

    def _set_display_color(self, updates):
        """単体の表示色を全アトリビュート検証後に反映する。

        Args:
            updates: アトリビュートと設定値の更新計画。
        """
        self._apply_display_color(self._prepare_display_color(updates))


class DagNodes(Nodes):
    """DAG参照の集合。表示操作と階層照会を共有する。"""

    item_class = DagNode

    _bulk_returns = {
        **Nodes._bulk_returns,
        "mpath": "list",
        "dagFn": "list",
        "getParentPath": "list",
        "parentPath": "list",
        "getParent": "list",
        "parent": "list",
        "getParents": "list",
        "parents": "list",
        "getInstances": "list",
        "instances": "list",
        "iterBreadthFirst": "list",
        "iterDepthFirst": "list",
        "getChildren": "list",
        "children": "list",
        "getShape": "list",
        "shape": "list",
        "getFullPath": "list",
        "fullPath": "list",
        "getPartialPath": "list",
        "partialPath": "list",
        "isVisible": "list",
        "getVisibility": "list",
        "visibility": "list",
        "getOutlinerVisibility": "list",
        "outlinerVisibility": "list",
        "getOutlinerColor": "list",
        "outlinerColor": "list",
        "getOverrideColor": "list",
        "overrideColor": "list",
        "getSkinClusters": "list",
        "skinClusters": "list",
        "getBindPoses": "list",
        "bindPoses": "list",
        "show": "self",
        "hide": "self",
        "setVisibility": "self",
        "setOutlinerVisibility": "self",
        "setOutlinerColor": "self",
        "setOverrideColor": "self",
    }
    _bulk_methods = {
        **Nodes._bulk_methods,
        "mpath": DagNode.mpath,
        "dagFn": DagNode.dagFn,
        "getParentPath": DagNode.getParentPath,
        "parentPath": DagNode.parentPath,
        "getParent": DagNode.getParent,
        "parent": DagNode.parent,
        "getParents": DagNode.getParents,
        "parents": DagNode.parents,
        "getInstances": DagNode.getInstances,
        "instances": DagNode.instances,
        "iterBreadthFirst": DagNode.iterBreadthFirst,
        "iterDepthFirst": DagNode.iterDepthFirst,
        "getChildren": DagNode.getChildren,
        "children": DagNode.children,
        "getShape": DagNode.getShape,
        "shape": DagNode.shape,
        "getFullPath": DagNode.getFullPath,
        "fullPath": DagNode.fullPath,
        "getPartialPath": DagNode.getPartialPath,
        "partialPath": DagNode.partialPath,
        "isVisible": DagNode.isVisible,
        "getVisibility": DagNode.getVisibility,
        "visibility": DagNode.visibility,
        "getOutlinerVisibility": DagNode.getOutlinerVisibility,
        "outlinerVisibility": DagNode.outlinerVisibility,
        "getOutlinerColor": DagNode.getOutlinerColor,
        "outlinerColor": DagNode.outlinerColor,
        "getOverrideColor": DagNode.getOverrideColor,
        "overrideColor": DagNode.overrideColor,
        "getSkinClusters": DagNode.getSkinClusters,
        "skinClusters": DagNode.skinClusters,
        "getBindPoses": DagNode.getBindPoses,
        "bindPoses": DagNode.bindPoses,
        "show": DagNode.show,
        "hide": DagNode.hide,
        "setVisibility": DagNode.setVisibility,
        "setOutlinerVisibility": DagNode.setOutlinerVisibility,
        "setOutlinerColor": DagNode.setOutlinerColor,
        "setOverrideColor": DagNode.setOverrideColor,
    }
    _bulk_per_item_only = frozenset()

    def mpath(self, *args, **kwargs):
        """各要素のmpathを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("mpath", args, kwargs)

    mpath.__signature__ = inspect.signature(DagNode.mpath)

    def dagFn(self, *args, **kwargs):
        """各要素のdagFnを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("dagFn", args, kwargs)

    dagFn.__signature__ = inspect.signature(DagNode.dagFn)

    def getParentPath(self, *args, **kwargs):
        """各要素のgetParentPathを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getParentPath", args, kwargs)

    getParentPath.__signature__ = inspect.signature(DagNode.getParentPath)

    def getParent(self, *args, **kwargs):
        """各要素のgetParentを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getParent", args, kwargs)

    getParent.__signature__ = inspect.signature(DagNode.getParent)

    def getParents(self, *args, **kwargs):
        """各要素のgetParentsを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getParents", args, kwargs)

    getParents.__signature__ = inspect.signature(DagNode.getParents)

    def getInstances(self, *args, **kwargs):
        """各要素のgetInstancesを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getInstances", args, kwargs)

    getInstances.__signature__ = inspect.signature(DagNode.getInstances)

    def iterBreadthFirst(self, *args, **kwargs):
        """各要素のiterBreadthFirstを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("iterBreadthFirst", args, kwargs)

    iterBreadthFirst.__signature__ = inspect.signature(DagNode.iterBreadthFirst)

    def iterDepthFirst(self, *args, **kwargs):
        """各要素のiterDepthFirstを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("iterDepthFirst", args, kwargs)

    iterDepthFirst.__signature__ = inspect.signature(DagNode.iterDepthFirst)

    def getChildren(self, *args, **kwargs):
        """各要素のgetChildrenを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getChildren", args, kwargs)

    getChildren.__signature__ = inspect.signature(DagNode.getChildren)

    def getShape(self, *args, **kwargs):
        """各要素のgetShapeを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getShape", args, kwargs)

    getShape.__signature__ = inspect.signature(DagNode.getShape)

    def getFullPath(self, *args, **kwargs):
        """各要素のgetFullPathを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getFullPath", args, kwargs)

    getFullPath.__signature__ = inspect.signature(DagNode.getFullPath)

    def getPartialPath(self, *args, **kwargs):
        """各要素のgetPartialPathを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getPartialPath", args, kwargs)

    getPartialPath.__signature__ = inspect.signature(DagNode.getPartialPath)

    def isVisible(self, *args, **kwargs):
        """各要素のisVisibleを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("isVisible", args, kwargs)

    isVisible.__signature__ = inspect.signature(DagNode.isVisible)

    def getVisibility(self, *args, **kwargs):
        """各要素のgetVisibilityを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getVisibility", args, kwargs)

    getVisibility.__signature__ = inspect.signature(DagNode.getVisibility)

    def setVisibility(self, *args, **kwargs):
        """各要素のsetVisibilityを同じ引数で呼び、コレクション自身を返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            DagNodes | list: コレクション自身。
        """
        return self._dispatch_shared("setVisibility", args, kwargs)

    setVisibility.__signature__ = inspect.signature(DagNode.setVisibility)

    def getOutlinerVisibility(self, *args, **kwargs):
        """各要素のgetOutlinerVisibilityを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getOutlinerVisibility", args, kwargs)

    getOutlinerVisibility.__signature__ = inspect.signature(DagNode.getOutlinerVisibility)

    def setOutlinerVisibility(self, *args, **kwargs):
        """各要素のsetOutlinerVisibilityを同じ引数で呼び、コレクション自身を返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            DagNodes | list: コレクション自身。
        """
        return self._dispatch_shared("setOutlinerVisibility", args, kwargs)

    setOutlinerVisibility.__signature__ = inspect.signature(DagNode.setOutlinerVisibility)

    def getSkinClusters(self, *args, **kwargs):
        """各要素のgetSkinClustersを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getSkinClusters", args, kwargs)

    getSkinClusters.__signature__ = inspect.signature(DagNode.getSkinClusters)

    def getBindPoses(self, *args, **kwargs):
        """各要素のgetBindPosesを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getBindPoses", args, kwargs)

    getBindPoses.__signature__ = inspect.signature(DagNode.getBindPoses)

    def show(self, *args, **kwargs):
        """各要素のshowを同じ引数で呼び、コレクション自身を返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            DagNodes | list: コレクション自身。
        """
        return self._dispatch_shared("show", args, kwargs)

    show.__signature__ = inspect.signature(DagNode.show)

    def hide(self, *args, **kwargs):
        """各要素のhideを同じ引数で呼び、コレクション自身を返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            DagNodes | list: コレクション自身。
        """
        return self._dispatch_shared("hide", args, kwargs)

    hide.__signature__ = inspect.signature(DagNode.hide)

    def getOverrideColor(self):
        """各対象のDrawing Overrides色。無効状態も保持順で返す。

        Returns:
            list[Color]: 各対象のDrawing Overrides色。無効状態も保持順で返す。
        """
        return [node.getOverrideColor() for node in self]

    @fast_edit
    @undoChunk("hlibNodesOverrideColor")
    def setOverrideColor(self, color, *, fast=False):
        """全対象へ同じ表示色を設定する。全対象の事前検証後に反映する。

        Args:
            color (Color | int | Iterable[float] | None): 単一色。Noneは無効化。
            fast (bool): TrueはUndoなしのAPI直接更新。既定False。
        Returns:
            DagNodes: 自身。
        Raises:
            ValueError: 色の値が不正。
            RuntimeError: 対象が無効、アトリビュートがない、編集不可または更新失敗。
        """
        from ..common.color import Color
        value = Color.coerce(color)
        return self._set_colors([value] * len(self), outliner=False)

    def getOutlinerColor(self):
        """各対象のOutliner色。無効状態も保持順で返す。

        Returns:
            list[Color]: 各対象のOutliner色。無効状態も保持順で返す。
        """
        return [node.getOutlinerColor() for node in self]

    @fast_edit
    @undoChunk("hlibNodesOutlinerColor")
    def setOutlinerColor(self, color, *, fast=False):
        """全対象へ同じOutliner色を設定する。

        Args:
            color (Color | int | Iterable[float] | None): 単一色。番号はRGBへ変換。
            fast (bool): TrueはUndoなし。既定False。
        Returns:
            DagNodes: 自身。全対象の事前検証・例外規則はset_override_colorと同じ。
        """
        from ..common.color import Color
        value = Color.coerce(color)
        return self._set_colors([value] * len(self), outliner=True)

    @fast_edit
    @undoChunk("hlibNodesOverrideColors")
    def setOverrideColors(self, colors, *, fast=False):
        """保持順に一色ずつDrawing Overridesを設定する。

        Args:
            colors (Iterable): 対象数と同数のColor・番号・RGB・Noneの列。
            fast (bool): TrueはUndoなし。既定False。
        Returns:
            DagNodes: 自身。
        Raises:
            ValueError: 件数不一致、不正な色、共有アトリビュートに異なる値を要求した場合。
            RuntimeError: 事前検証または反映失敗。実行時失敗の自動ロールバックはしない。
        """
        from ..common.color import Color
        return self._set_colors([Color.coerce(color) for color in colors], outliner=False)

    @fast_edit
    @undoChunk("hlibNodesOutlinerColors")
    def setOutlinerColors(self, colors, *, fast=False):
        """保持順に一色ずつOutliner色を設定する。

        Args:
            colors (Iterable): 対象数と同数の色指定の列。
            fast (bool): TrueはUndoなし。既定False。
        Returns:
            DagNodes: 自身。事前検証・例外規則はset_override_colorsと同じ。
        """
        from ..common.color import Color
        return self._set_colors([Color.coerce(color) for color in colors], outliner=True)

    @_getter_alias(getParentPath)
    def parentPath(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getParentPath(*args, **kwargs)

    @_getter_alias(getParent)
    def parent(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getParent(*args, **kwargs)

    @_getter_alias(getParents)
    def parents(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getParents(*args, **kwargs)

    @_getter_alias(getInstances)
    def instances(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getInstances(*args, **kwargs)

    @_getter_alias(getChildren)
    def children(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getChildren(*args, **kwargs)

    @_getter_alias(getShape)
    def shape(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getShape(*args, **kwargs)

    @_getter_alias(getFullPath)
    def fullPath(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getFullPath(*args, **kwargs)

    @_getter_alias(getPartialPath)
    def partialPath(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getPartialPath(*args, **kwargs)

    @_getter_alias(getVisibility)
    def visibility(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getVisibility(*args, **kwargs)

    @_getter_alias(getOutlinerVisibility)
    def outlinerVisibility(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getOutlinerVisibility(*args, **kwargs)

    @_getter_alias(getSkinClusters)
    def skinClusters(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getSkinClusters(*args, **kwargs)

    @_getter_alias(getBindPoses)
    def bindPoses(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getBindPoses(*args, **kwargs)

    @_getter_alias(getOverrideColor)
    def overrideColor(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getOverrideColor(*args, **kwargs)

    @_getter_alias(getOutlinerColor)
    def outlinerColor(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getOutlinerColor(*args, **kwargs)

    def _set_colors(self, colors, *, outliner):
        """全色・対象を検証し、共有アトリビュートの競合を除いて更新計画を実行する。

        Args:
            colors: 適用する色の成分または対象ごとの色の列。
            outliner: TrueはOutliner色、FalseはDrawing Overridesを扱う。
        """
        if len(colors) != len(self):
            raise ValueError("Color count must match node count")
        plans, seen = [], {}
        for index, (node, color) in enumerate(zip(self, colors)):
            try:
                updates = node._display_color_updates(color, outliner=outliner)
                plugs = node._prepare_display_color(updates)
                key = node.getUuid()
                if key in seen:
                    if seen[key] != updates:
                        raise ValueError("Conflicting colors for shared instance attributes")
                    continue
                seen[key] = updates
                plans.append((index, node, plugs))
            except ValueError:
                raise
            except Exception as exc:
                raise RuntimeError(f"{type(self).__name__} color validation failed at item {index}: {exc}") from exc
        for index, node, plugs in plans:
            try:
                node._apply_display_color(plugs)
            except Exception as exc:
                raise RuntimeError(f"{type(self).__name__} color update failed at item {index}: {exc}") from exc
        return self
