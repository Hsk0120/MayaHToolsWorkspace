# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""指定の生成先へ標準scalar演算を構築する。"""

from typing import Any, Callable, Optional
from ..decorator import _edit_context
from ..nodes.container import Container
from ..plugs.plug import Plug
from mlib.nodes.node import Node
import contextlib



class ScalarGraph:
    """定数とPlugを組み合わせる単位なし数値グラフのビルダー。

    各構築メソッドの通常経路は一つのUndoチャンクにまとめ、例外時は巻戻しを試みる。
    ``fast=True`` は生成関数へ ``fast=True`` を渡して作成し、値の設定と接続をOpenMayaで
    直接行う(Undoなし・途中失敗の巻戻しなし)。containerを所有先にした場合は
    Container.createNodeがfastを持たないため、fast=Trueは変更前にNotImplementedErrorとする。
    """
    container: Optional[Container]
    _createNode: Callable[..., Any]
    def __init__(self, container: str | Container | None = ..., *, createNode: Callable | None = ...) -> None:
        """containerまたは生成関数のどちらか一方を保持する。

        Args:
            container (str | Container | None): 演算ノードの所有先。
            createNode (Callable | None): (node_type, name=...)を受け取りNodeを返す生成関数。
                構築メソッドへfast=Trueを渡す場合は、キーワード ``fast=True`` も受け取る必要がある
                (例: ``mlib.createNode``)。

        Raises:
            TypeError: createNodeが呼び出せない値の場合。
            ValueError: containerとcreateNodeを両方指定した、またはどちらも指定しない場合。
        """
        ...
    def sum(self, role: str, left: float | str | Plug, right: float | str | Plug, subtract: bool = ..., *, fast: bool = ...) -> Plug:
        """加減算を構築する。

        Args:
            role (str): 演算名。
            left (float | str | Plug): 左辺。
            right (float | str | Plug): 右辺。
            subtract (bool): Trueなら減算。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Plug: 改名に追従する出力プラグ。

        Raises:
            TypeError: fastがbool以外の場合。
            NotImplementedError: containerを所有先にしてfast=Trueを指定した場合。
        """
        ...
    def multiply(self, role: str, left: float | str | Plug, right: float | str | Plug, operation: int = ..., *, fast: bool = ...) -> Plug:
        """乗除算・累乗を構築する。

        Args:
            role (str): 演算名。
            left (float | str | Plug): 左辺。
            right (float | str | Plug): 右辺。
            operation (int): 1は乗算、2は除算、3は累乗。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Plug: 改名に追従する出力プラグ。

        Raises:
            TypeError: fastがbool以外の場合。
            NotImplementedError: containerを所有先にしてfast=Trueを指定した場合。
        """
        ...
    def condition(self, role: str, left: float | str | Plug, right: float | str | Plug, yes: float | str | Plug, no: float | str | Plug, *, fast: bool = ...) -> Plug:
        """大小比較によって値を選択する。

        Args:
            role (str): 演算名。
            left (float | str | Plug): 比較の左辺。
            right (float | str | Plug): 比較の右辺。
            yes (float | str | Plug): 左辺が右辺より大きい場合の値。
            no (float | str | Plug): それ以外の値。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Plug: 改名に追従する出力プラグ。

        Raises:
            TypeError: fastがbool以外の場合。
            NotImplementedError: containerを所有先にしてfast=Trueを指定した場合。
        """
        ...
    def _edit(self, name: str, fast: bool) -> contextlib.AbstractContextManager:
        """fastを検証し、構築全体のUndo範囲を返す。

        Args:
            name (str): 通常経路のUndoチャンク名。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            contextlib.AbstractContextManager: 通常はundoTransaction、fastはnullcontext。

        Raises:
            TypeError: fastがbool以外の場合。
            NotImplementedError: containerを所有先にしてfast=Trueを指定した場合。
        """
        ...
    def _node(self, kind: str, role: str, fast: bool = ...) -> Node:
        """設定した生成先へ演算ノードを作成する。

        Args:
            kind (str): 標準ノード型。
            role (str): 演算の識別名。
            fast (bool): Trueは生成関数へ ``fast=True`` を渡す。Falseは従来どおり渡さない。

        Returns:
            Node: 作成したノード。
        """
        ...
    @staticmethod
    def _feed(value: float | str | Plug, destination: Plug | str, fast: bool = ...) -> None:
        """入力へ定数を設定するかプラグを接続する。

        Args:
            value (float | str | Plug): 定数または入力プラグ名。
            destination (Plug | str): 接続先アトリビュート。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            None: 値を返さない。
        """
        ...
