"""Maya の標準コンストレイントに共通するターゲット・ウェイトの取得と設定を扱う。"""

from ..decorators._fast import fast_edit

import maya.cmds as cmds

from ..decorators.undo import undoChunk
from .node import Node
from .transform import Transform


class Constraint(Transform):
    """標準コンストレイントのターゲットとウェイトを取得・設定する共通ラッパー。

    具象クラスは各 nodeType ごとに専用ファイル(parentConstraint.py 等)で定義する。
    """

    __hlib_public__ = True

    def targets(self):
        """ターゲットを Maya の問い合わせ順に取得する。

        Returns:
            list[Node]: ターゲットのラッパー。登録がなければ空リスト。
        """
        names = getattr(cmds, self.type())(self.fullName(), query=True, targetList=True) or []
        return [Node(name) for name in names]

    def weightAliases(self):
        """各ターゲットのウェイトアトリビュートの別名を取得する。

        Returns:
            list[str]: targets() と同じ順序のアトリビュート別名。
        """
        return getattr(cmds, self.type())(self.fullName(), query=True, weightAliasList=True) or []

    def weightPlugs(self):
        """ターゲットのウェイトプラグを取得する。

        Returns:
            list[Plug]: targets() と同じ順序のプラグ。set() で値を変更できる。
        """
        return [self.plug(alias) for alias in self.weightAliases()]

    def getWeights(self):
        """ターゲットの現在のウェイトを取得する。

        Returns:
            list[float]: targets() と同じ順序の値。正規化は行わない。
        """
        return [plug.get() for plug in self.weightPlugs()]

    def getWeight(self, target):
        """指定ターゲットの現在のウェイトを取得する。

        Args:
            target (Node | str): この拘束に登録されたターゲット。
        Returns:
            float: 正規化していないウェイト値。
        Raises:
            ValueError: ターゲットが登録されていない場合。
        """
        from ..nodes.node import Node as _InputNode
        requested = _InputNode._resolve_input(target).fullName()
        for node, plug in zip(self.targets(), self.weightPlugs()):
            if node.fullName() == requested:
                return plug.get()
        raise ValueError(f"Target not found on this constraint: {requested}")

    @fast_edit
    @undoChunk("hlibConstraintSetWeight")
    def setWeight(self, weight, *targets, fast=False):
        """ターゲットのウェイトをまとめて設定する。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            weight (float): 設定するウェイト値。
            targets (Node | str): 値を設定するターゲット。省略時は全ターゲットに設定する。

        Returns:
            Constraint: 自身。

        Raises:
            ValueError: 指定したターゲットがこのコンストレイントのターゲットに含まれない場合。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        from ..nodes.node import Node as _InputNode
        from ..nodes.node import Nodes as _InputNodes
        weightPlugs = self.weightPlugs()
        if not targets:
            for plug in weightPlugs:
                plug.set(weight)
            return self
        requested = {_InputNode._resolve_input(target).fullName() for target in _InputNodes._resolve_inputs(targets)}
        available = {node.fullName(): plug for node, plug in zip(self.targets(), weightPlugs)}
        missing = requested - available.keys()
        if missing:
            raise ValueError(f"Targets not found on this constraint: {sorted(missing)}")
        # 全ターゲットを解決してから更新する。無効な指定で部分更新しない。
        for name, plug in available.items():
            if name in requested:
                plug.set(weight)
        return self
