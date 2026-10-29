# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Maya の標準コンストレイントに共通するターゲット・ウェイトの取得と設定を扱う。"""

import maya.cmds as cmds
from ..decorator import _edit_context
from .node import Node, Nodes
from .transform import Transform
from mlib.plugs.plug import Plug



class Constraint(Transform):
    """標準コンストレイントのノード参照を保持し、ターゲットと生ウェイトを扱う。

    具象型はparentConstraintなどのMaya nodeTypeごとに定義する。ターゲットと
    weight aliasの対応は各標準コマンドの問い合わせ順を使い、独自に並べ替えない。
    コンストレイント先の探索やリグ構築を担当するクラスではない。

    fast対応のウェイト書込みはPlugへ委譲するが、ターゲット/alias照会には
    cmdsを使う。fast呼出し全体がOpenMayaだけになるわけではない。
    """
    def getTargets(self) -> list[Node]:
        """Maya標準コンストレイントコマンドで、登録ターゲットを問い合わせる。

        nodeTypeに対応するコマンドのtargetList順を保つ。targetのマルチアトリビュートの論理番号で
        独自にソートせず、getWeightAliases()の対応順として使う。

        Returns:
            list[Node]: 新しいNode参照のリスト。登録がなければ空。値やノードの複製ではない。
        """
        ...
    def getWeightAliases(self) -> list[str]:
        """登録ターゲットに対応するweight aliasを標準コマンドで問い合わせる。

        Returns:
            list[str]: getTargets()と同じ問い合わせ順のalias名。
                ノード上の全aliasを列挙するgetAliases()とは対象が異なる。
        """
        ...
    def getWeightPlugs(self) -> list[Plug]:
        """ターゲットのウェイトプラグを取得する。

        Returns:
            list[Plug]: getTargets() と同じ順序のプラグ。set() で値を変更できる。
        """
        ...
    def getWeights(self) -> list[float]:
        """ターゲットの現在のウェイトを取得する。

        Returns:
            list[float]: getTargets() と同じ順序の値。正規化は行わない。
        """
        ...
    def getWeight(self, target: Node | str) -> float:
        """指定ターゲットの現在のウェイトを取得する。

        Args:
            target (Node | str): このコンストレイントに登録されたターゲット。

        Returns:
            float: 正規化していないウェイト値。

        Raises:
            ValueError: ターゲットが登録されていない場合。
        """
        ...
    def setWeight(self, weight: float, *targets: Node | str, fast: bool = ...) -> Constraint:
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
            TypeError: fastがbool以外の場合。
            ValueError: 明示ターゲットがこのコンストレイントに登録されていない場合。
        """
        ...
