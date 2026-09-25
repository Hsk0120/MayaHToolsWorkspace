"""Maya の標準コンストレイントに共通するターゲット・ウェイトの取得と設定を扱う。"""

from ..decorators._fast import fast_edit

import maya.cmds as cmds

from .._core.coerce import to_node
from ..decorators.undo import undo_chunk
from .node import Node


class Constraint(Node):
    """標準コンストレイントのターゲットとウェイトを取得・設定する共通ラッパー。

    具象クラスは各 nodeType ごとに専用ファイル(parentConstraint.py 等)で定義する。
    """

    __hlib_public__ = True

    def targets(self):
        """ターゲットを Maya の問い合わせ順に取得する。

        Returns:
            list[Node]: ターゲットのラッパー。登録がなければ空リスト。
        """
        names = getattr(cmds, self.type())(self.full_name(), query=True, targetList=True) or []
        return [Node(name) for name in names]

    def weight_aliases(self):
        """各ターゲットのウェイト属性の別名を取得する。

        Returns:
            list[str]: targets() と同じ順序の属性別名。
        """
        return getattr(cmds, self.type())(self.full_name(), query=True, weightAliasList=True) or []

    def weight_plugs(self):
        """ターゲットのウェイトプラグを取得する。

        Returns:
            list[Plug]: targets() と同じ順序のプラグ。set() で値を変更できる。
        """
        return [self.plug(alias) for alias in self.weight_aliases()]

    def weights(self):
        """ターゲットの現在のウェイトを取得する。

        Returns:
            list[float]: targets() と同じ順序の値。正規化は行わない。
        """
        return [plug.get() for plug in self.weight_plugs()]

    @fast_edit
    @undo_chunk("hlibConstraintSetWeight")
    def set_weight(self, weight, *targets, fast=False):
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
        weight_plugs = self.weight_plugs()
        if not targets:
            for plug in weight_plugs:
                plug.set(weight)
            return self
        remaining = {to_node(target).full_name() for target in targets}
        for target_node, plug in zip(self.targets(), weight_plugs):
            if target_node.full_name() in remaining:
                plug.set(weight)
                remaining.discard(target_node.full_name())
        if remaining:
            raise ValueError(f"Targets not found on this constraint: {sorted(remaining)}")
        return self
