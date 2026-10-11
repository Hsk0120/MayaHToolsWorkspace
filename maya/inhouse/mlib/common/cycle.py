"""Mayaが検出した循環経路と現在の接続関係を扱う。"""

import math

import maya.cmds as cmds

from .._core.getterAlias import _getter_alias
from ..nodes.dagNode import DagNode
from ..nodes.node import Node
from ..plugs.plug import Plug


_SEPARATOR = "__HTOOLS_CYCLE_SEPARATOR__"


class Cycle:
    """検出時の循環経路を保持する。完全な循環とは限らず部分経路も含む。"""

    def __init__(self, plugs):
        """経路を保持する。手動指定時は循環の成立を検証しない。

        Args:
            plugs (Iterable[Plug | str]): 検出順のアトリビュート。
        """
        from ..cmds.getPlug import getPlug

        self._plugs = tuple(getPlug(plug) for plug in plugs)

    @classmethod
    def find(cls, targets=None, include_dag=True, seconds=10.0, first_only=False):
        """シーンを変更せず循環候補を検出する。

        Args:
            targets (Iterable[str | Node | Plug] | None): Noneでシーン全体。単数も可。
            include_dag (bool): DAGの親子関係を検出に含める。
            seconds (float): 検索時間の上限（秒）。
            first_only (bool): 最初の完全なサイクルだけを要求する。

        Returns:
            list[Cycle]: 検出経路。時間制限や実行時依存により0件でも無循環を保証しない。

        Raises:
            ValueError: 空の対象または不正な時間上限。
            TypeError: 対象の型が不正。
            RuntimeError: 検索または検出アトリビュートの解決に失敗。
        """
        from ..cmds.getPlug import getPlug

        seconds = float(seconds)
        if not math.isfinite(seconds) or seconds <= 0:
            raise ValueError("検索時間は0より大きい有限の秒数を指定してください。")
        names = []
        if targets is not None:
            if isinstance(targets, (str, Node, Plug)):
                targets = [targets]
            for target in targets:
                if isinstance(target, (Node, Plug)):
                    obj = target
                elif isinstance(target, str):
                    obj = getPlug(target) if "." in target else Node(target)
                else:
                    raise TypeError("ノードまたはアトリビュートを指定してください。")
                if not isinstance(obj, (Node, Plug)):
                    raise TypeError("ノードまたはアトリビュートを指定してください。")
                names.append(obj.getFullName() if isinstance(obj, Plug) else obj.getName())
            if not names:
                raise ValueError("調査するノードを選択してください。")
        options = dict(list=True, dag=include_dag, secondary=True,
                       timeLimit="{}sec".format(seconds), listSeparator=_SEPARATOR,
                       firstCycleOnly=first_only)
        if targets is None:
            options["all"] = True
        raw = cmds.cycleCheck(*names, **options) or []
        paths = []
        current = []
        for name in raw:
            if name == _SEPARATOR:
                if current:
                    paths.append(current)
                    current = []
            else:
                current.append(name)
        if current:
            paths.append(current)
        return [cls(path) for path in paths]

    @property
    def plugs(self):
        """tuple[Plug, ...]: 検出時の順序を保持する経路。名前変更には追従する。"""
        return self._plugs

    def getConnections(self):
        """経路上のアトリビュートに関係する現在の実接続を照会する。

        Returns:
            list[tuple[Plug, Plug]]: 接続元・接続先。経路外の接続も含む。

        Raises:
            RuntimeError: 保持するアトリビュートが削除済みなどで照会に失敗。
        """
        pairs = {}
        for plug in self.plugs:
            source = plug.getSourceWithConversion()
            edges = [(source, plug)] if source is not None else []
            edges.extend((plug, destination) for destination in plug.getDestinationsWithConversions())
            for source, destination in edges:
                pairs[(source.getFullName(), destination.getFullName())] = (source, destination)
        return [pairs[key] for key in sorted(pairs)]

    def getParents(self):
        """関連ノードの現在のDAG親子関係を照会する。

        Returns:
            list[tuple[DagNode, DagNode]]: 親・子。インスタンスの全親を含む。

        Raises:
            RuntimeError: 保持するアトリビュートが削除済みなどで照会に失敗。
        """
        pairs = {}
        for plug in self.plugs:
            node = plug.getNode()
            if isinstance(node, DagNode):
                for name in cmds.listRelatives(node.getFullName(), allParents=True, fullPath=True) or []:
                    parent = Node(name)
                    pairs[(parent.getFullName(), node.getFullName())] = (parent, node)
        return [pairs[key] for key in sorted(pairs)]

    @_getter_alias(getConnections)
    def connections(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getConnections(*args, **kwargs)

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
