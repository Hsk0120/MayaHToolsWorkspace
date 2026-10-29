# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Maya containerによる計算ノードの所有管理。"""

import maya.api.OpenMaya as om2
import maya.cmds as cmds
from ..decorator import undoTransaction
from ..plugs.plug import Plug
from .node import Node, Nodes, _resolve_node
from typing import Iterable



class _ContainerMixin:
    """containerBase 系のノード(:class:`Container`・:class:`~mlib.nodes.dagContainer.DagContainer`)が
    共有する所属・公開名の操作。

    Node を継承しない混ぜ込み用のクラスで、単独では使わない。Container は ``_ContainerMixin`` と
    Node、DagContainer は Transform と Container を基底に持つため、``isinstance(x, Container)`` は
    container・dagContainer の両方で True のまま。

    接続先を自動収集するラッパーではなく、Mayaのcontainer所属と公開名のBindを扱う。
    メンバーや公開Plugの照会はOpenMaya、所属・公開名の編集はcmdsを使う。

    編集はUndo有効を前提とするundoTransactionでまとめ、失敗時にUndoでの復旧を試みる。
    復旧処理自体の失敗まで保証するものではない。fast引数は提供しない。
    createNodeの内部ノード生成にも通常のUndo可能な編集を使う。
    """
    _CONTAINER_FLAGS: dict
    @classmethod
    def create(cls, name: str = ..., members: str | Node | Iterable[Node | str] = ...) -> Container:
        """containerを作成し、指定ノードを所属させる(作成 + :meth:`addMembers`)。

        ``cmds.container`` 専用の特化ビルダーで、現在のcontainer文脈への自動所属などcmdsの規則に従う。
        Container は ``cmds.container(name=...)``、DagContainer は ``type="dagContainer"`` で作る。
        空のcontainerだけが必要なら ``mlib.createNode("container", name=...)`` でも作れる。
        fast引数は持たない(cmds.containerにOpenMayaの同等機能が無い)。

        Args:
            name (str): 希望名。衝突時はMayaが一意名にする。位置引数でも指定できる。
            members (str | Node | Iterable[Node | str]): 作成後に所属させるノード。省略時は空のまま。

        Returns:
            Container: 呼び出したクラスの新しい所有ノード(DagContainer.create は DagContainer)。
        """
        ...
    def getMembers(self) -> list[Node]:
        """Maya containerへ直接所属するノード参照を取得する。

        MFnContainerNode.getMembers()の列挙を使い、接続先や入れ子containerの内容を
        再帰的に展開しない。DAG階層の子孫を列挙する操作でもない。

        Returns:
            list[Node]: 新しいNode参照のリスト。ノードを複製せず、列挙順を独自にソートしない。
        """
        ...
    def addMembers(self, *members: str | Node | Iterable[Node | str]) -> Container:
        """指定ノードを所有下へ追加する。別containerからは強制移動しない。

        Args:
            *members (str | Node | Iterable[Node | str]): 所有するノード。

        Returns:
            Container: 自身。
        """
        ...
    def removeMembers(self, *members: Node | str | Iterable[Node], force: bool = ...) -> Container:
        """指定ノードの直接所属を解除する。

        全件の所属を変更前に検査し、force=Trueでも未所属は拒否する。ノード自体は削除しない。
        ネスト時は通常、親containerの所属へ移る。

        Args:
            *members (Node | str | Iterable[Node]): 解除するメンバー。
            force (bool): Trueなら全containerから解除する。ロック解除ではない。

        Returns:
            Container: 自身。

        Raises:
            ValueError: 未所属ノードを含む場合。
        """
        ...
    def createNode(self, type: str, name: str | None = ...) -> Node:
        """標準ノードを生成し所有下へまとめる。

        Args:
            type (str): Maya nodeType。
            name (str | None): 希望名。省略時はcontainer名に型名を付加。

        Returns:
            Node: 作成したノード(実際のnodeTypeに対応するラッパー)。

        Raises:
            ValueError: typeが空文字列・文字列以外の場合。
            RuntimeError: Mayaが認識しないtypeの場合(unknownノードを残さない)。
        """
        ...
    def removeContainer(self) -> None:
        """直接メンバーの所属を外してから、container自身を解除する。

        先にメンバーを外して、MayaのremoveContainer処理によるメンバー削除を避ける。
        自身のアトリビュート接続は失われ、出力の迂回接続や設定移送は行わない。
        通常のdeleteとは削除範囲が異なり、成功後の自身の参照は無効になる。

        Returns:
            None: メンバーノードを返す操作ではない。
        """
        ...
    def publishName(self, name: str) -> str:
        """未Bindの公開名を作る。

        Args:
            name (str): 希望する公開名。

        Returns:
            str: 作成した公開名。
        """
        ...
    def getPublishedAttrs(self) -> dict[str, Plug | None]:
        """containerの公開アトリビュート名とBind先の内部Plugを取得する。

        未Bindの公開名をNoneで登録し、getPublishedPlugs()の対応でBind済み名を補う。
        公開ノードのアンカーは扱わず、Plug値の取得や転送アトリビュートの生成は行わない。

        Returns:
            dict[str, Plug | None]: 新しい対応辞書。Plugは内部アトリビュートへの参照。
                辞書を変更しても公開名やBindは更新されない。
        """
        ...
    def bindAttr(self, name: str, plug: Plug | str) -> Plug:
        """未Bindの公開名へ内部PlugをBindする。

        Args:
            name (str): 既存の未Bind公開名。
            plug (Plug | str): このcontainerへ直接所属するノードのアトリビュート。

        Returns:
            Plug: 対応付けた内部アトリビュート。

        Raises:
            ValueError: nameが未Bindの公開名でない、またはPlugの所有ノードが直接メンバーでない場合。
        """
        ...
    def publishAndBind(self, name: str, plug: Plug | str) -> Plug:
        """公開名を作成し、内部PlugへBindする。

        Args:
            name (str): 新しい公開名。
            plug (Plug | str): このcontainerへ直接所属するノードのアトリビュート。

        Returns:
            Plug: 対応付けた内部アトリビュート。

        Raises:
            ValueError: nameが既存の公開名、またはPlugの所有ノードが直接メンバーでない場合。
        """
        ...
    def unbindAttr(self, name: str) -> None:
        """対応付けだけを解除し、公開名を残す。

        Args:
            name (str): Bind済みの公開名。

        Returns:
            None: 値を返さない。

        Raises:
            ValueError: nameが公開名でない、または未Bindの場合。何も変更しない。
        """
        ...
    def unpublishName(self, name: str) -> None:
        """未Bindの公開名を削除する。

        Args:
            name (str): 未Bindの公開名。

        Returns:
            None: 値を返さない。

        Raises:
            ValueError: nameが公開名でない、またはBind済みの場合。何も変更しない。
        """
        ...


class Container(_ContainerMixin, Node):
    """containerノードの参照を保持し、直接所属と公開名/内部Plugの対応を管理する。

    所属・公開名の操作(create・getMembers・addMembers・removeMembers・createNode・removeContainer・
    publishName・getPublishedAttrs・bindAttr・publishAndBind・unbindAttr・unpublishName)は
    :class:`_ContainerMixin` に定義し、:class:`~mlib.nodes.dagContainer.DagContainer` と共有する。
    """
