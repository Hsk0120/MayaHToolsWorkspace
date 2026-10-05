"""TransformとShapeに共通するDAG階層へのアクセスを提供する。"""

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from .._core.collection import bulk_api
from .._core.registry import collection_export
from ..decorators._fast import fast_edit
from ..decorators.undo import undoChunk
from .node import Node, Nodes


class DagNode(Node):
    """DAGノードの共通基底。具象ラッパーの型登録は変更しない。"""

    __hlib_public__ = True

    def mpath(self):
        """保持するインスタンスのDAGパスを取得する。

        Returns:
            om2.MDagPath: この参照が保持するDAGパス。

        Raises:
            RuntimeError: 保持していたパスが無効な場合。他のインスタンスへ切り替えない。
        """
        return self._current_dag_path()

    def dagFn(self):
        """保持するDAGパスに対応するfunction setを取得する。

        Returns:
            om2.MFnDagNode: このインスタンスのfunction set。

        Raises:
            RuntimeError: 保持していたパスが無効な場合。
        """
        return om2.MFnDagNode(self.mpath())

    def parentPath(self):
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

    def parent(self, step=1):
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

    def fullPath(self):
        """str: 保持するDAGインスタンスの完全パス。"""
        return self.mpath().fullPathName()

    def children(self, shapes=False, intermediates=False):
        """非TransformのDAGノードでは空の子リストを返す。

        Args:
            shapes (bool): Transform側のShape取得指定。
            intermediates (bool): Transform側の中間ノード取得指定。
        Returns:
            list: 空リスト。Transformではオーバーライドする。
        """
        return []

    def shape(self, idx=0, intermediates=False):
        """Shape自身を返す。Transformでは指定Shapeを取得する。

        Args:
            idx (int): Shape自身では無視する。
            intermediates (bool): Shape自身では無視する。
        Returns:
            DagNode | None: Shapeなら自身、それ以外はNone。
        """
        return self if self.mnode().hasFn(om2.MFn.kShape) else None

    def partialPath(self):
        """str: 保持するDAGインスタンスの最短一意パス。"""
        return self.mpath().partialPathName()

    def isVisible(self):
        """bool: 親階層を含むDAGの表示状態。"""
        return self.mpath().isVisible()

    def show(self):
        """DagNode: visibilityを有効にして自身を返す。"""
        return self.setVisibility(True)

    def hide(self):
        """DagNode: visibilityを無効にして自身を返す。"""
        return self.setVisibility(False)

    def getVisibility(self):
        """bool: 自身のvisibilityアトリビュート値。親や表示レイヤーを含む最終可視性ではない。"""
        return bool(self.plug("visibility").get())

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
        self.plug("visibility").set(state)
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
        return not bool(self.plug("hiddenInOutliner").get())

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
        self.plug("hiddenInOutliner").set(not state)
        return self

    def getOutlinerColor(self):
        """Color: このノードのOutliner色。無効時はdisabledモード。"""
        from ..ui.color import Color
        if not self.plug("useOutlinerColor").get():
            return Color.disabled()
        return Color(rgb=self.plug("outlinerColor").get())

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
        from ..ui.color import Color
        value = Color.coerce(color)
        self._set_display_color(self._display_color_updates(value, outliner=True))
        return self

    def getOverrideColor(self):
        """Color: 自身のDrawing Overrides色。最終表示色ではない。

        親・表示レイヤー・選択ハイライトは合成しない。
        アトリビュートがない場合はRuntimeError。無効時はdisabledモードを返す。
        """
        from ..ui.color import Color
        if not self.plug("overrideEnabled").get():
            return Color.disabled()
        if self.plug("overrideRGBColors").get():
            return Color(rgb=self.plug("overrideColorRGB").get())
        return Color(index=self.plug("overrideColor").get())

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
        from ..ui.color import Color
        value = Color.coerce(color)
        self._set_display_color(self._display_color_updates(value))
        return self

    @staticmethod
    def _display_color_updates(value, outliner=False):
        """正規化済みColorから対象アトリビュートと値の更新計画を作る。"""
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
        """全アトリビュートの存在・書込み可否を検証してPlugと値の計画を返す。"""
        if not self.isValid():
            raise RuntimeError("Cannot color an invalid node")
        if om2.MFnDependencyNode(self.mnode()).isLocked:
            raise RuntimeError("Cannot color a locked node: " + self.fullName())
        if any(not cmds.objExists(self.fullName() + "." + name) for name, _ in updates):
            raise RuntimeError("Node does not have the requested display color attributes")
        plugs = [(self.plug(name), value) for name, value in updates]
        for plug, value in plugs:
            plug._require_writable()
        return plugs

    @staticmethod
    def _apply_display_color(plugs):
        """検証済みの計画を現在のfastモードで適用する。実行時失敗は伝播する。"""
        for plug, value in plugs:
            plug.set(value)

    def _set_display_color(self, updates):
        """単体の表示色を全アトリビュート検証後に反映する。"""
        self._apply_display_color(self._prepare_display_color(updates))


@collection_export()
@bulk_api(
    DagNode,
    reads=(
        'mpath',
        'dagFn',
        'parentPath',
        'parent',
        'children', 'shape',
        'fullPath', 'partialPath', 'isVisible',
        'getVisibility',
        'getOutlinerVisibility',
        'getOutlinerColor',
        'getOverrideColor',
    ),
    writes=(
        'show', 'hide',
        'setVisibility',
        'setOutlinerVisibility',
        'setOutlinerColor',
        'setOverrideColor',
    ),
)
class DagNodes(Nodes):
    """DAG参照の集合。表示操作と階層照会を共有する。"""

    item_class = DagNode

    def getOverrideColor(self):
        """list[Color]: 各対象のDrawing Overrides色。無効状態も保持順で返す。"""
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
        from ..ui.color import Color
        value = Color.coerce(color)
        return self._set_colors([value] * len(self), outliner=False)

    def getOutlinerColor(self):
        """list[Color]: 各対象のOutliner色。無効状態も保持順で返す。"""
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
        from ..ui.color import Color
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
        from ..ui.color import Color
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
        from ..ui.color import Color
        return self._set_colors([Color.coerce(color) for color in colors], outliner=True)

    def _set_colors(self, colors, *, outliner):
        """全色・対象を検証し、共有アトリビュートの競合を除いて更新計画を実行する。"""
        if len(colors) != len(self):
            raise ValueError("Color count must match node count")
        plans, seen = [], {}
        for index, (node, color) in enumerate(zip(self, colors)):
            try:
                updates = node._display_color_updates(color, outliner=outliner)
                plugs = node._prepare_display_color(updates)
                key = node.uuid()
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
