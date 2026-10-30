"""Maya containerによる計算ノードの所有管理。"""

from typing import TYPE_CHECKING

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from ..decorator import undoTransaction
from ..plugs.plug import Plug
from .node import Node, Nodes, _resolve_node


# 実行時は Node を継承しない混ぜ込みとし、型検査では Node のメソッドを参照できるようにする。
class _ContainerMixin(Node if TYPE_CHECKING else object):
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

    #: create が ``cmds.container`` へ渡す型の指定。派生クラスが上書きする(container は指定なし)。
    _CONTAINER_FLAGS = {}

    @classmethod
    def create(cls, name="container", members=()):
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
        with undoTransaction("mlib" + cls.__name__ + "Create"):
            container = cls(cmds.container(name=name, **cls._CONTAINER_FLAGS))
            if members:
                container.addMembers(members)
            return container

    def getMembers(self):
        """Maya containerへ直接所属するノード参照を取得する。

        MFnContainerNode.getMembers()の列挙を使い、接続先や入れ子containerの内容を
        再帰的に展開しない。DAG階層の子孫を列挙する操作でもない。

        Returns:
            list[Node]: 新しいNode参照のリスト。ノードを複製せず、列挙順を独自にソートしない。
        """
        # Node(obj)と同じ解決(DAGは最初のパス)・型選択を、生成の入口の再判定なしで行う。
        return [Node._wrap_resolved(*_resolve_node(obj)) for obj in om2.MFnContainerNode(self.mnode()).getMembers()]

    @undoTransaction("mlibContainerAddMembers")
    def addMembers(self, *members):
        """指定ノードを所有下へ追加する。別containerからは強制移動しない。

        Args:
            *members (str | Node | Iterable[Node | str]): 所有するノード。

        Returns:
            Container: 自身。
        """
        nodes = Nodes._resolve_inputs(members)
        if nodes:
            cmds.container(
                self.getFullName(), edit=True, addNode=[Node._resolve_input(n).getFullName() for n in nodes]
            )
        return self

    def removeMembers(self, *members, force=False):
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
        with undoTransaction("mlibContainerRemoveMembers"):
            nodes = [Node._resolve_input(node) for node in Nodes._resolve_inputs(members)]
            # Nodeの等価なら__hash__も等しいため、集合での所属判定はリストの`in`と同じ結果になる。
            current = set(self.getMembers())
            if any(node not in current for node in nodes):
                raise ValueError("nodes must all be members of this container")
            if nodes:
                cmds.container(self.getFullName(), edit=True,
                               removeNode=[node.getFullName() for node in nodes], force=force)
            return self

    @undoTransaction("mlibContainerCreateNode")
    def createNode(self, type, name=None):
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
        node = Node._create_node(type, {"name": name or self.getName() + "_" + type, "skipSelect": True})
        self.addMembers(node)
        return node

    @undoTransaction("mlibContainerRemoveContainer")
    def removeContainer(self):
        """直接メンバーの所属を外してから、container自身を解除する。

        先にメンバーを外して、MayaのremoveContainer処理によるメンバー削除を避ける。
        自身のアトリビュート接続は失われ、出力の迂回接続や設定移送は行わない。
        通常のdeleteとは削除範囲が異なり、成功後の自身の参照は無効になる。

        Returns:
            None: メンバーノードを返す操作ではない。
        """
        # removeContainer単独では未接続のDGメンバーも削除される版がある。
        # 所属を先に外し、メンバーの生存を保証してから空の箱を除去する。
        members = self.getMembers()
        if members:
            cmds.container(self.getFullName(), edit=True,
                           removeNode=[node.getFullName() for node in members])
        cmds.container(self.getFullName(), edit=True, removeContainer=True)

    @undoTransaction("mlibContainerPublishName")
    def publishName(self, name):
        """未Bindの公開名を作る。

        Args:
            name (str): 希望する公開名。

        Returns:
            str: 作成した公開名。
        """
        if name in self.getPublishedAttrs():
            raise ValueError(f"Published name already exists: {name}")
        result = cmds.container(self.getFullName(), edit=True, publishName=name)
        return result[0] if isinstance(result, (list, tuple)) else result

    def getPublishedAttrs(self):
        """containerの公開アトリビュート名とBind先の内部Plugを取得する。

        未Bindの公開名をNoneで登録し、getPublishedPlugs()の対応でBind済み名を補う。
        公開ノードのアンカーは扱わず、Plug値の取得や転送アトリビュートの生成は行わない。

        Returns:
            dict[str, Plug | None]: 新しい対応辞書。Plugは内部アトリビュートへの参照。
                辞書を変更しても公開名やBindは更新されない。
        """
        fn = om2.MFnContainerNode(self.mnode())
        result = dict.fromkeys(fn.getPublishedNames(False))
        plugs, names = fn.getPublishedPlugs()
        for plug, name in zip(plugs, names):
            result[name] = Plug._resolve_input(plug)
        return result

    @undoTransaction("mlibContainerBindAttr")
    def bindAttr(self, name, plug):
        """未Bindの公開名へ内部PlugをBindする。

        Args:
            name (str): 既存の未Bind公開名。
            plug (Plug | str): このcontainerへ直接所属するノードのアトリビュート。

        Returns:
            Plug: 対応付けた内部アトリビュート。

        Raises:
            ValueError: nameが未Bindの公開名でない、またはPlugの所有ノードが直接メンバーでない場合。
        """
        published = self.getPublishedAttrs()
        if name not in published or published[name] is not None:
            raise ValueError(f"Expected an unbound published name: {name}")
        plug = Plug._resolve_input(plug)
        if plug.getNode() not in self.getMembers():
            raise ValueError("plug must belong to a member node")
        cmds.container(self.getFullName(), edit=True, bindAttr=(plug.getFullName(), name))
        return plug

    @undoTransaction("mlibContainerPublishAndBind")
    def publishAndBind(self, name, plug):
        """公開名を作成し、内部PlugへBindする。

        Args:
            name (str): 新しい公開名。
            plug (Plug | str): このcontainerへ直接所属するノードのアトリビュート。

        Returns:
            Plug: 対応付けた内部アトリビュート。

        Raises:
            ValueError: nameが既存の公開名、またはPlugの所有ノードが直接メンバーでない場合。
        """
        if name in self.getPublishedAttrs():
            raise ValueError(f"Published name already exists: {name}")
        plug = Plug._resolve_input(plug)
        if plug.getNode() not in self.getMembers():
            raise ValueError("plug must belong to a member node")
        cmds.container(self.getFullName(), edit=True, publishAndBind=(plug.getFullName(), name))
        return plug

    @undoTransaction("mlibContainerUnbindAttr")
    def unbindAttr(self, name):
        """対応付けだけを解除し、公開名を残す。

        Args:
            name (str): Bind済みの公開名。

        Returns:
            None: 値を返さない。

        Raises:
            ValueError: nameが公開名でない、または未Bindの場合。何も変更しない。
        """
        plug = self.getPublishedAttrs().get(name)
        if plug is None:
            raise ValueError(f"Expected a bound published name: {name}")
        cmds.container(self.getFullName(), edit=True, unbindAttr=(plug.getFullName(), name))

    @undoTransaction("mlibContainerUnpublishName")
    def unpublishName(self, name):
        """未Bindの公開名を削除する。

        Args:
            name (str): 未Bindの公開名。

        Returns:
            None: 値を返さない。

        Raises:
            ValueError: nameが公開名でない、またはBind済みの場合。何も変更しない。
        """
        published = self.getPublishedAttrs()
        if name not in published or published[name] is not None:
            raise ValueError(f"Expected an unbound published name: {name}")
        cmds.container(self.getFullName(), edit=True, unpublishName=name)


class Container(_ContainerMixin, Node):
    """containerノードの参照を保持し、直接所属と公開名/内部Plugの対応を管理する。

    所属・公開名の操作(create・getMembers・addMembers・removeMembers・createNode・removeContainer・
    publishName・getPublishedAttrs・bindAttr・publishAndBind・unbindAttr・unpublishName)は
    :class:`_ContainerMixin` に定義し、:class:`~mlib.nodes.dagContainer.DagContainer` と共有する。
    """
