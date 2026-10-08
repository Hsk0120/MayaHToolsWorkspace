"""Maya の標準コンストレイントに共通するターゲット・ウェイトの取得と設定を扱う。"""

import maya.cmds as cmds

from .._core.getterAlias import _getter_alias
from ..common._fast import fast_edit
from ..decorator import undoChunk
from .node import Node
from .transform import Transform


class Constraint(Transform):
    """標準コンストレイントのターゲットとウェイトを取得・設定する共通ラッパー。

    具象クラスは各 nodeType ごとに専用ファイル(parentConstraint.py 等)で定義する。
    """

    def getTargets(self):
        """ターゲットを Maya の問い合わせ順に取得する。

        Returns:
            list[Node]: ターゲットのラッパー。登録がなければ空リスト。
        """
        names = getattr(cmds, self.getType())(self.getFullName(), query=True, targetList=True) or []
        return [Node(name) for name in names]

    def getWeightAliases(self):
        """各ターゲットのウェイトアトリビュートの別名を取得する。

        Returns:
            list[str]: getTargets() と同じ順序のアトリビュート別名。
        """
        return getattr(cmds, self.getType())(self.getFullName(), query=True, weightAliasList=True) or []

    def getWeightPlugs(self):
        """ターゲットのウェイトプラグを取得する。

        Returns:
            list[Plug]: getTargets() と同じ順序のプラグ。set() で値を変更できる。
        """
        return [self.getPlug(alias) for alias in self.getWeightAliases()]

    def getWeights(self):
        """ターゲットの現在のウェイトを取得する。

        Returns:
            list[float]: getTargets() と同じ順序の値。正規化は行わない。
        """
        return [plug.get() for plug in self.getWeightPlugs()]

    def getWeight(self, target):
        """指定ターゲットの現在のウェイトを取得する。

        Args:
            target (Node | str): この拘束に登録されたターゲット。
        Returns:
            float: 正規化していないウェイト値。
        Raises:
            ValueError: ターゲットが登録されていない場合。
        """
        from .node import Node as _InputNode
        requested = _InputNode._resolve_input(target).getFullName()
        for node, plug in zip(self.getTargets(), self.getWeightPlugs()):
            if node.getFullName() == requested:
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
        from .node import Node as _InputNode
        from .node import Nodes as _InputNodes
        weightPlugs = self.getWeightPlugs()
        if not targets:
            for plug in weightPlugs:
                plug.set(weight)
            return self
        requested = {_InputNode._resolve_input(target).getFullName() for target in _InputNodes._resolve_inputs(targets)}
        available = {node.getFullName(): plug for node, plug in zip(self.getTargets(), weightPlugs)}
        missing = requested - available.keys()
        if missing:
            raise ValueError(f"Targets not found on this constraint: {sorted(missing)}")
        # 全ターゲットを解決してから更新する。無効な指定で部分更新しない。
        for name, plug in available.items():
            if name in requested:
                plug.set(weight)
        return self

    @_getter_alias(getTargets)
    def targets(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getTargets(*args, **kwargs)

    @_getter_alias(getWeightAliases)
    def weightAliases(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getWeightAliases(*args, **kwargs)

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

    @_getter_alias(getWeight)
    def weight(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getWeight(*args, **kwargs)
