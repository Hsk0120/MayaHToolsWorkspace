"""Base Maya node wrapper."""

import maya.api.OpenMaya as om2

from ..utils import error


def _node_type_of(node):
    """ノード名、MObject、または MDagPath から Maya nodeType 名を得る。"""
    if isinstance(node, str):
        selection = om2.MSelectionList()
        try:
            selection.add(node)
        except RuntimeError as original_error:
            message = f"ノードが見つかりません: {node}"
            error(message)
            raise RuntimeError(message) from original_error
        mobject = selection.getDependNode(0)
    elif isinstance(node, om2.MDagPath):
        mobject = node.node()
    elif isinstance(node, om2.MObject):
        mobject = node
    else:
        raise TypeError("node には名前、MObject、または MDagPath を指定してください")
    return om2.MFnDependencyNode(mobject).typeName


class Node:
    """Maya の dependency node / DAG node を表す共通ラッパー。

    Args:
        node (str | om2.MObject | om2.MDagPath): Maya ノード名、MObject、または
            MDagPath。

    Raises:
        TypeError: 対応していない型の値を指定した場合。
    """

    _registry = None  #: Hlib.__init__ が構築後に注入する NodeRegistry。

    def __new__(cls, node, *args, **kwargs):
        registry = cls._registry
        if registry is not None:
            node_type = _node_type_of(node)
            resolved_class = registry.wrapper_class(node_type)
            if resolved_class is not cls:
                return resolved_class(node, *args, **kwargs)
        return super().__new__(cls)

    def __init__(self, node):
        """ノード入力を解決し、MObject と必要に応じた MDagPath を保持する。"""
        self._mobject = None
        self._dag_path = None
        self._resolve(node)

    def _resolve(self, node):
        """ノード名、MObject、または MDagPath を内部 API オブジェクトへ変換する。"""
        if isinstance(node, str):
            selection = om2.MSelectionList()
            try:
                selection.add(node)
            except RuntimeError as original_error:
                message = f"ノードが見つかりません: {node}"
                error(message)
                raise RuntimeError(message) from original_error
            self._mobject = selection.getDependNode(0)
            if self._mobject.hasFn(om2.MFn.kDagNode):
                self._dag_path = selection.getDagPath(0)
            return
        if isinstance(node, om2.MDagPath):
            self._dag_path = om2.MDagPath(node)
            self._mobject = self._dag_path.node()
            return
        if isinstance(node, om2.MObject):
            self._mobject = om2.MObject(node)
            if self._mobject.hasFn(om2.MFn.kDagNode):
                self._dag_path = om2.MFnDagNode(self._mobject).getPath()
            return
        raise TypeError("node には名前、MObject、または MDagPath を指定してください")

    def is_valid(self):
        """Maya シーン上でノードが有効か判定する。

        Returns:
            bool: ノードハンドルが有効な場合は ``True``。
        """
        return bool(
            self._mobject is not None
            and not self._mobject.isNull()
            and om2.MObjectHandle(self._mobject).isValid()
        )

    def is_alive(self):
        """ノードが削除待ちではなく生存しているか判定する。

        Returns:
            bool: ノードが生存している場合は ``True``。
        """
        return bool(
            self._mobject is not None
            and not self._mobject.isNull()
            and om2.MObjectHandle(self._mobject).isAlive()
        )

    def mobject(self):
        """保持している Maya API 2.0 MObject を返す。

        Returns:
            om2.MObject | None: ラップ対象の MObject。
        """
        return self._mobject

    def type(self):
        """Maya の nodeType 名を返す。

        Returns:
            str: 対応する Maya nodeType。
        """
        return om2.MFnDependencyNode(self._mobject).typeName

    def plug(self, name):
        """属性パスに対応する Plug を取得する。

        Args:
            name (str): 属性名または Maya が解決可能な属性パス。

        Returns:
            Plug: 解決した属性プラグ。

        Raises:
            ValueError: 空文字列または文字列以外を指定した場合。
            RuntimeError: ノードが無効な場合。
            AttributeError: 属性を解決できない場合。
        """
        if not isinstance(name, str) or not name:
            raise ValueError("name には空でない属性パスを指定してください")
        if not self.is_valid():
            raise RuntimeError("無効なノードの属性にはアクセスできません")
        from ..plugs.plug import Plug

        try:
            mplug = om2.MFnDependencyNode(self._mobject).findPlug(name, False)
        except RuntimeError as error:
            raise AttributeError(f"属性が見つかりません: {self.name}.{name}") from error
        return Plug(self, mplug)

    def attr(self, name):
        """属性プラグを取得する ``plug`` の別名。

        Args:
            name (str): 属性名または属性パス。

        Returns:
            Plug: 解決した属性プラグ。
        """
        return self.plug(name)

    def has_attr(self, name):
        """属性パスを解決できるか判定する。

        Args:
            name (str): 属性名または属性パス。

        Returns:
            bool: 属性を解決できる場合は ``True``。
        """
        try:
            self.plug(name)
        except (AttributeError, RuntimeError, ValueError):
            return False
        return True

    @property
    def uuid(self):
        """ノードの Maya UUID を返す。

        Returns:
            str | None: 有効なノードの UUID。無効な場合は ``None``。
        """
        if not self.is_valid():
            return None
        return om2.MFnDependencyNode(self._mobject).uuid().asString()

    @property
    def name(self):
        """Maya の最短一意ノード名を返す。

        Returns:
            str: 無効なノードでは空文字列。
        """
        if not self.is_valid():
            return ""
        if self._dag_path is not None:
            return self._dag_path.partialPathName()
        return om2.MFnDependencyNode(self._mobject).name()

    @property
    def full_name(self):
        """Maya の完全 DAG パスまたは DG ノード名を返す。

        Returns:
            str: 無効なノードでは空文字列。
        """
        if not self.is_valid():
            return ""
        if self._dag_path is not None:
            return self._dag_path.fullPathName()
        return om2.MFnDependencyNode(self._mobject).name()

    def __str__(self):
        """Maya の最短一意ノード名を文字列として返す。"""
        return self.name

    def __repr__(self):
        """デバッグ用にクラス名とノード名を含む表現を返す。"""
        if self.is_valid():
            return f"{type(self).__name__}({self.name!r})"
        return f"<{type(self).__name__} invalid>"

    def __getattr__(self, name):
        """通常属性にない名前を Maya Plug として動的に解決する。

        Args:
            name (str): 取得しようとした Python 属性名。

        Returns:
            Plug: 解決した Maya 属性プラグ。

        Raises:
            AttributeError: private 名または存在しない Maya 属性を指定した場合。
        """
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self.plug(name)
        except AttributeError as error:
            raise AttributeError(f"属性が見つかりません: {self.name}.{name}") from error


