"""TransformとShapeに共通するDAG階層へのアクセスを提供する。"""

import inspect

import maya.api.OpenMaya as om2
import maya.api.OpenMayaAnim as oma2
import maya.cmds as cmds

from ..decorator import _flag_aliases, _fast_edit, undoChunk
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

    def collectSkinClusters(self):
        """自身に関連するSkinClusterを操作可能なコレクションで取得する。

        Shape/Transformは変形対象、Jointはinfluence接続の既存getSkinClustersを使う。
        getSkinClustersのlist返却や検索範囲は変更しない。

        Returns:
            SkinClusters: 重複を除き、既存照会の順を保った参照コレクション。

        Raises:
            RuntimeError: 対象が無効、または既存照会に失敗した場合。
        """
        from .skinCluster import SkinClusters

        return SkinClusters(self.getSkinClusters())

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

    def getChildren(self, shapes=False, intermediates=False, *, allDescendents=False,
                    order="depthFirst", leaves=False, includeSelf=False, underWorld=False):
        """直接の子、または指定順の子孫をDAGパスを保持して取得する。

        Args:
            shapes (bool): Shapeも含める。既定はTransformのみ。
            intermediates (bool): 中間オブジェクトを含める。
            allDescendents (bool): Trueは子孫全体、Falseは直接の子だけ。
            order (str): depthFirstまたはbreadthFirst。兄弟間はDAGの子順。
            leaves (bool): 子Transformを持たないTransformだけを再帰取得する。
                Shapeの有無は葉の判定に関与しない。shapes=Trueとは併用しない。
            includeSelf (bool): 自身も取得対象に含める。自身が葉の場合も適用する。
            underWorld (bool): Shape下のアンダーワールドも探索する。

        Returns:
            list[DagNode]: 保持するインスタンスのパスに沿ったノード。対象なしは空リスト。

        Raises:
            TypeError: 検索フラグがboolでない場合。
            ValueError: 探索順が不正、またはleavesとshapesを併用した場合。
        """
        flags = (allDescendents, leaves, includeSelf, underWorld)
        if any(type(value) is not bool for value in flags):
            raise TypeError("DAG search flags must be bool")
        if order not in ("depthFirst", "breadthFirst"):
            raise ValueError("order must be 'depthFirst' or 'breadthFirst'")
        if leaves and shapes:
            raise ValueError("leaves selects transforms and cannot be combined with shapes")
        if not self.isValid():
            return []
        recursive = allDescendents or leaves
        from collections import deque
        pending = deque([(self, 0)])
        result = []
        while pending:
            node, depth = pending.popleft() if order == "breadthFirst" else pending.pop()
            is_shape = node.mnode().hasFn(om2.MFn.kShape)
            children = node._traversal_children(shapes, intermediates, underWorld) if recursive or depth == 0 else []
            selected = (includeSelf or depth > 0) and (shapes or not is_shape)
            if selected and (not leaves or not any(
                    child.mnode().hasFn(om2.MFn.kTransform) for child in children)):
                result.append(node)
            if recursive or depth == 0:
                rows = [(child, depth + 1) for child in children]
                pending.extend(rows if order == "breadthFirst" else reversed(rows))
        return result

    @_flag_aliases(index="idx")
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

    @_fast_edit
    @undoChunk("mlibNodeSetVisible")
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

    @_fast_edit
    @undoChunk("mlibNodeSetOutlinerVisibility")
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

    def _direct_children(self, shapes, intermediates):
        """直接の子をAPIで列挙し、インスタンスの親パスを維持する。

        Args:
            shapes (bool): Shapeも列挙するか。
            intermediates (bool): 中間オブジェクトも含めるか。

        Returns:
            list[DagNode]: 条件に合う直接の子。非Transformでは空リスト。
        """
        path = self.mpath()
        if not path.node().hasFn(om2.MFn.kTransform):
            return []
        fn = om2.MFnDagNode(path)
        result = []
        for index in range(fn.childCount()):
            obj = fn.child(index)
            if not shapes and not obj.hasFn(om2.MFn.kTransform):
                continue
            if not intermediates and om2.MFnDagNode(obj).isIntermediateObject:
                continue
            child = om2.MDagPath(path)
            child.push(obj)
            result.append(Node(child))
        return result

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
        result.extend(self._direct_children(shapes, intermediates))
        return result


class DagNodes(Nodes):
    """DAG参照の集合。表示操作と階層照会を共有する。"""

    item_class = DagNode

    # 単数の呼出し先と返却方針を同じ行で宣言し、追加漏れを防ぐ。
    _bulk_entries = {
        "mpath": (DagNode.mpath, "list"),
        "dagFn": (DagNode.dagFn, "list"),
        "getParentPath": (DagNode.getParentPath, "list"),
        "getParent": (DagNode.getParent, "list"),
        "getParents": (DagNode.getParents, "list"),
        "getInstances": (DagNode.getInstances, "list"),
        "getChildren": (DagNode.getChildren, "list"),
        "getShape": (DagNode.getShape, "list"),
        "getFullPath": (DagNode.getFullPath, "list"),
        "getPartialPath": (DagNode.getPartialPath, "list"),
        "isVisible": (DagNode.isVisible, "list"),
        "getVisibility": (DagNode.getVisibility, "list"),
        "getOutlinerVisibility": (DagNode.getOutlinerVisibility, "list"),
        "getSkinClusters": (DagNode.getSkinClusters, "list"),
        "collectSkinClusters": (DagNode.collectSkinClusters, "list"),
        "getBindPoses": (DagNode.getBindPoses, "list"),
        "show": (DagNode.show, "self"),
        "hide": (DagNode.hide, "self"),
        "setVisibility": (DagNode.setVisibility, "self"),
        "setOutlinerVisibility": (DagNode.setOutlinerVisibility, "self"),
    }
    _bulk_methods = {
        **Nodes._bulk_methods,
        **{name: entry[0] for name, entry in _bulk_entries.items()},
    }
    _bulk_returns = {
        **Nodes._bulk_returns,
        **{name: entry[1] for name, entry in _bulk_entries.items()},
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

    def collectSkinClusters(self):
        """各DAGノードのSkinClusterを保持順で集約し、重複を除く。

        既存getSkinClustersの要素ごとのlist返却や、Jointsの既存集約は変更しない。
        この明示集約は、複数geometryで共有されるSkinClusterを一回だけ操作する用途。

        Returns:
            SkinClusters: 各要素のgetSkinClusters順で初出を保つコレクション。

        Raises:
            RuntimeError: 無効な対象、または既存照会の失敗。
        """
        from .skinCluster import SkinClusters

        return SkinClusters(skin for node in self for skin in node.getSkinClusters())

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
