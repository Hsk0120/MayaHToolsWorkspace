"""Maya の標準コンストレイントに共通するターゲット・ウェイトの取得と設定を扱う。"""

from contextlib import nullcontext

import maya.cmds as cmds

from ..decorator import undoChunk
from .node import Node
from .transform import Transform


class Constraint(Transform):
    """標準コンストレイントのノード参照を保持し、ターゲットと生ウェイトを扱う。

    具象型はparentConstraintなどのMaya nodeTypeごとに定義する。ターゲットと
    weight aliasの対応は各標準コマンドの問い合わせ順を使い、独自に並べ替えない。
    コンストレイント先の探索やリグ構築を担当するクラスではない。

    fast対応のウェイト書込みはPlugへ委譲するが、ターゲット/alias照会には
    cmdsを使う。fast呼出し全体がOpenMayaだけになるわけではない。
    """

    def getTargets(self):
        """Maya標準コンストレイントコマンドで、登録ターゲットを問い合わせる。

        nodeTypeに対応するコマンドのtargetList順を保つ。target配列の論理番号で
        独自にソートせず、getWeightAliases()の対応順として使う。

        Returns:
            list[Node]: 新しいNode参照のリスト。登録がなければ空。値やノードの複製ではない。
        """
        names = getattr(cmds, self.getType())(self.getFullName(), query=True, targetList=True) or []
        return [Node(name) for name in names]

    def getWeightAliases(self):
        """登録ターゲットに対応するweight aliasを標準コマンドで問い合わせる。

        Returns:
            list[str]: getTargets()と同じ問い合わせ順のalias名。
                ノード上の全aliasを列挙するgetAliases()とは対象が異なる。
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
            target (Node | str): このコンストレイントに登録されたターゲット。

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

    def setWeight(self, weight, *targets, fast=False):
        """登録ターゲットの生ウェイトを、Mayaのターゲット順で更新する。

        明示ターゲットは全件を解決して登録の有無を検査し、重複をまとめてから更新する。
        照合は解決した完全名で行い、呼出し側の指定順には並べ替えない。
        書込み可否と値は各Plug.set()へ逐次委譲するため、後半の失敗では先行更新が
        残り得る。全Plugの事前検査や自動ロールバックは行わない。

        Args:
            weight (float): 全対象へ設定する値。ここでは正規化や0〜1への制限を行わない。
            targets (Node | str): 更新対象。省略時は全ターゲット。対象がなければ値を検証せず返す。
            fast (bool): TrueはPlug書込みをOpenMayaで行いUndoへ記録しない。
                Falseは通常更新をUndo有効時にまとめ、Undo設定は変えない。
                ターゲット/alias照会にはfastでもcmdsを使う。

        Returns:
            Constraint: 自身。

        Raises:
            ValueError: 明示ターゲットがこのコンストレイントに登録されていない場合。
            TypeError: fastがboolでない場合。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibConstraintSetWeight"):
            from .node import Node as _InputNode
            from .node import Nodes as _InputNodes
            weight_plugs = self.getWeightPlugs()
            if not targets:
                for plug in weight_plugs:
                    plug.set(weight, fast=fast)
                return self
            requested = {_InputNode._resolve_input(target).getFullName() for target in _InputNodes._resolve_inputs(targets)}
            available = {node.getFullName(): plug for node, plug in zip(self.getTargets(), weight_plugs)}
            missing = requested - available.keys()
            if missing:
                raise ValueError(f"Targets not found on this constraint: {sorted(missing)}")
            # 全ターゲットを解決してから更新する。無効な指定で部分更新しない。
            for name, plug in available.items():
                if name in requested:
                    plug.set(weight, fast=fast)
            return self
