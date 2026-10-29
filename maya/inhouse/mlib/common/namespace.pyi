# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Maya の名前空間の参照・作成・移動・削除を提供する。"""

from contextlib import contextmanager
import maya.api.OpenMaya as om2
import maya.cmds as cmds
from ..decorator import undoChunk
from typing import Any, ContextManager, Iterator
from mlib.nodes.node import Node
import types



class Namespace:
    """Maya namespaceを表すシーンエンティティ。"""
    def __init__(self, name: str | Namespace = ...) -> None:
        """Namespace名を正規化してラッパーを初期化する。

        名前を保持するだけで、シーン内の名前空間を作成・存在確認しない。

        Args:
            name (str | Namespace): 名前空間名または既存ラッパー。既定の : はルート。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: 文字列・Namespace 以外の場合。
            ValueError: 空文字列の場合。
        """
        ...
    def __repr__(self) -> str:
        """Namespaceのデバッグ表現を返す。

        Returns:
            str: Namespace と保持名を含む文字列表現。
        """
        ...
    def __str__(self) -> str:
        """Namespaceの絶対名を返す。

        Returns:
            str: 正規化済みの保持名。存在確認はしない。
        """
        ...
    def __eq__(self, other: object) -> bool | types.NotImplementedType:
        """Namespace名を基準に同一性を判定する。

        Args:
            other (object): 比較対象。

        Returns:
            bool | types.NotImplementedType: Namespace 同士は保持名を比較する。異なる型では NotImplemented。
        """
        ...
    def __hash__(self) -> int:
        """Namespace名を使ったハッシュ値を返す。

        Returns:
            int: 現在の保持名のハッシュ。rename/move により変化するため、集合や辞書キーとして保持中の名前変更は避ける。
        """
        ...
    @classmethod
    def getCurrent(cls) -> Namespace:
        """カレントNamespaceを取得する。

        Returns:
            Namespace: 現在のカレントNamespace。
        """
        ...
    @classmethod
    def create(cls, name: str | Namespace, parent: str | Namespace = ...) -> Namespace:
        """指定先の名前空間を作成する。既存なら作成せず参照を返す。

        カレントNamespaceは変更しない。/は:と同じ区切りとして扱う。
        cmds.namespaceでUndo有効時に一つのチャンクへ記録する。fast引数は持たない。

        Args:
            name (str | Namespace): 相対名はparent配下、絶対名とNamespace参照はparentを無視する。
                多段名も指定できる。
            parent (str | Namespace): 作成先の親。相対文字列はカレントから解決する。
                既定はルート(:)。存在しない親も再帰的に作成する。

        Returns:
            Namespace: 新規・既存の作成先の完全名を保持するラッパー。

        Raises:
            ValueError: nameまたはparentが不正な場合。
            RuntimeError: Mayaが作成を拒否した場合。

        Note:
            不正文字(``-``・空白・先頭の数字・``#`` 等)はMayaの規則で置き換え、
            置き換え後の名前が既存なら末尾に番号を付ける。戻り値はMayaが実際に作った名前。
        """
        ...
    @property
    def name(self) -> str:
        """正規化済みの絶対Namespace名を返す。

        Returns:
            str: 先頭が : の保持名。
        """
        ...
    def exists(self) -> bool:
        """NamespaceがMayaシーンに存在するか判定する。

        Returns:
            bool: 保持名の名前空間が現在のシーンに存在すれば True。
        """
        ...
    def getParent(self) -> Namespace | None:
        """親Namespaceを返す。root namespaceの親は ``None``。

        Returns:
            Namespace | None: 名前から求めた親。ルート自身では None。親の存在は確認しない。
        """
        ...
    def getChildren(self) -> list[Namespace]:
        """直下の子Namespaceを取得する。

        Returns:
            list[Namespace]: 直下の子。自身が存在しない場合は空リスト。
        """
        ...
    def getNodes(self, recurse: bool = ...) -> list[Node]:
        """Namespace内のNodeをmlib wrapperとして返す。

        Args:
            recurse (bool): ``True`` の場合は子Namespace内も含める。

        Returns:
            list[Node]: 名前空間内のノードラッパー。自身が存在しない場合は空リスト。
        """
        ...
    def setCurrent(self) -> Namespace:
        """カレントNamespaceを自身へ切り替える。

        cmdsでUndo有効時に一つのチャンクへ記録する。fast引数は持たない。

        Returns:
            Namespace: 自身。

        Raises:
            RuntimeError: 自身が存在しない場合。
        """
        ...
    def asCurrent(self) -> ContextManager[Namespace]:
        """カレントNamespaceを自身へ一時的に切り替える。

        終了時は例外の有無によらず復元を試みる。元の名前空間が削除済みなら復元しない。
        復元処理の失敗は送出され、ブロック内の例外を置き換え得る。

        Yields:
            Namespace: 自身。

        Raises:
            RuntimeError: 自身が存在しない、またはMayaが切替え・復元を拒否した場合。
        """
        ...
    def rename(self, name: str | Namespace) -> Namespace:
        """Namespace自身の名前を変更する。

        cmdsでUndo有効時に一つのチャンクへ記録する。fast引数は持たない。

        Args:
            name (str | Namespace): 新しい名前。最後の階層名だけを使用し、現在の親は維持する。

        Returns:
            Namespace: 保持名を更新した自身。

        Raises:
            ValueError: ルートの変更、または名前が不正な場合。
            RuntimeError: 移動先が既存、親が存在しない、または Maya 操作が失敗した場合。
        """
        ...
    def move(self, parent: str | Namespace = ...) -> Namespace:
        """Namespaceを指定した親Namespaceへ移動する。

        cmdsでUndo有効時に一つのチャンクへ記録する。fast引数は持たない。

        Args:
            parent (str | Namespace): 移動先の既存の親名前空間。末尾の自身の名前は維持する。

        Returns:
            Namespace: 保持名を更新した自身。

        Raises:
            ValueError: ルートの移動、または parent が不正な場合。
            RuntimeError: 親が存在しない、移動先が既存、または Maya 操作が失敗した場合。
        """
        ...
    def remove(self, destination: str | Namespace = ...) -> Namespace:
        """内容を移動してNamespaceを削除する。

        名前が衝突するノードは、移動時にMayaの規則(cmdsのforce移動)で末尾に番号を付けて改名する。
        cmdsでUndo有効時に一つのチャンクへ記録する。fast引数は持たない。

        Args:
            destination (str | Namespace): 内容を移動する既存の名前空間。既定はルート。

        Returns:
            Namespace: 内容を受け取った移動先。自身の保持名は削除前のまま。

        Raises:
            ValueError: ルートの削除、または destination が不正な場合。
            RuntimeError: 移動先が存在しない、または Maya 操作が失敗した場合。
        """
        ...
    @classmethod
    def _create(cls, name: str | Namespace, parent: str | Namespace) -> Namespace:
        """createの本体。Undoチャンクは呼出し側が管理する。

        Args:
            name (str | Namespace): createのname。
            parent (str | Namespace): createのparent。

        Returns:
            Namespace: 作成先の完全名を保持するラッパー。
        """
        ...
    @staticmethod
    def _normalize(name: str) -> str:
        """Namespace名をMayaの絶対表記へ正規化する。

        Args:
            name (str): 正規化する名前。

        Returns:
            str: / を : に置き換え、両端の : を除いて先頭に : を付けた名前。区切り文字だけなら :。
        """
        ...
    def _move_contents(self, target: Namespace) -> None:
        """Namespaceの内容を別Namespaceへ移し、元Namespaceを削除する。

        移動先を作成し、force=True で内容を移して元を削除する。自身の保持名はここでは更新しない。

        Args:
            target (Namespace): 新規作成する移動先。親は存在している必要がある。Undoチャンクは呼出し側が管理する。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: 移動先が既存、親が存在しない、または Maya 操作が失敗した場合。
        """
        ...
