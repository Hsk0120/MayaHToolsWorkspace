"""Maya の reference ノードを扱う。"""

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from .._core.registry import node_wrapper
from ..decorators.undo import undo_chunk
from .node import Node


@node_wrapper("reference")
class Reference(Node):
    """Maya の reference ノードラッパー。参照ファイルの照会・ロード制御を提供する。"""

    def reference_fn(self):
        """MFnReference を取得する。

        Returns:
            om2.MFnReference: この reference ノードの function set。
        """
        return om2.MFnReference(self.mobject())

    def filename(self, resolved=True, with_copy_number=False):
        """参照ファイルのパスを取得する。

        Args:
            resolved (bool): True の場合、パス変数などを解決した実際のパスを返す。
                False の場合はシーンに保存されている未解決のパスを返す。
            with_copy_number (bool): True の場合、同じファイルを複数回参照した
                際のコピー番号(``{1}`` 等)を含める。

        Returns:
            str: 参照ファイルのパス。
        """
        return self.reference_fn().fileName(resolved, with_copy_number, False)

    def namespace(self):
        """参照内容が読み込まれている Namespace を取得する。

        Returns:
            Namespace: 参照の名前空間。
        """
        # namespaces.namespace が ..nodes を逆方向 import しないため単純な import で足りるが、
        # hlib 内の他の相互依存箇所と合わせて遅延 import で統一する。
        from ..namespaces import Namespace

        return Namespace(self.reference_fn().associatedNamespace(False))

    def is_loaded(self):
        """参照が現在ロードされているか判定する。

        Returns:
            bool: ロード済みなら True。
        """
        return self.reference_fn().isLoaded()

    def nodes(self):
        """この参照が持ち込んだノードを取得する。

        Returns:
            list[Node]: 参照内のノードラッパー。

        Raises:
            RuntimeError: 参照が現在アンロードされている場合。
        """
        if not self.is_loaded():
            raise RuntimeError("Cannot enumerate nodes of an unloaded reference")
        return [Node(mobject) for mobject in self.reference_fn().nodes()]

    def parent_reference(self):
        """親の Reference を取得する(ネストした参照の場合)。

        Returns:
            Reference | None: 親参照。トップレベルの参照では None。
        """
        parent = self.reference_fn().parentReference()
        if parent.isNull():
            return None
        return Reference(parent)

    def children(self):
        """自身を親に持つ、直下にネストした子 Reference を取得する。

        Returns:
            list[Reference]: 子参照。無ければ空リスト。孫以下は含めない。
        """
        from ..files.references import list_references

        own_name = self.full_name
        children = []
        for reference in list_references():
            parent = reference.parent_reference()
            if parent is not None and parent.full_name == own_name:
                children.append(reference)
        return children

    def root(self):
        """ネストの最上位(トップレベル)の Reference を取得する。

        Returns:
            Reference: トップレベルの参照。自身がトップレベルならそのまま自身。
        """
        reference = self
        parent = reference.parent_reference()
        while parent is not None:
            reference = parent
            parent = reference.parent_reference()
        return reference

    def is_root(self):
        """トップレベル(親を持たない)の参照か判定する。

        Returns:
            bool: 親参照が無ければ True。
        """
        return self.parent_reference() is None

    def edit_strings(self, successful=True, failed=False):
        """このReferenceに対するEdit(MELコマンド文字列)一覧を取得する。

        Args:
            successful (bool): 実際に適用された(成功した)Editを含めるか。
            failed (bool): 適用に失敗したEditを含めるか。

        Returns:
            list[str]: Editを表すMELコマンド文字列。無ければ空リスト。
        """
        return cmds.referenceQuery(
            self.name(), editStrings=True,
            successfulEdits=successful, failedEdits=failed,
        ) or []

    def edit_nodes(self, successful=True, failed=False):
        """Editの影響を受けたノードのフルパス名一覧を取得する。

        Args:
            successful (bool): 実際に適用された(成功した)Editを含めるか。
            failed (bool): 適用に失敗したEditを含めるか。

        Returns:
            list[str]: Editが加えられたノードのフルパス名(重複あり得る)。無ければ空リスト。
        """
        return cmds.referenceQuery(
            self.name(), editNodes=True,
            successfulEdits=successful, failedEdits=failed,
        ) or []

    def edit_attrs(self, successful=True, failed=False):
        """Editの影響を受けた属性の短縮名一覧を取得する。

        Maya の ``referenceQuery -editAttrs`` 自体がノード名を含まない属性名の
        みを返す(コンパウンド属性の子を編集した場合は親の短縮名になる)。
        どのノードの属性かは ``edit_nodes()`` や ``edit_strings()`` と合わせて判断する。

        Args:
            successful (bool): 実際に適用された(成功した)Editを含めるか。
            failed (bool): 適用に失敗したEditを含めるか。

        Returns:
            list[str]: Edit対象の属性の短縮名(重複あり得る)。無ければ空リスト。
        """
        return cmds.referenceQuery(
            self.name(), editAttrs=True,
            successfulEdits=successful, failedEdits=failed,
        ) or []

    @undo_chunk("hlibReferenceLoad")
    def load(self):
        """参照をロードする。

        Returns:
            Reference: 自身。

        Raises:
            RuntimeError: Maya がロードを拒否した場合。
        """
        cmds.file(loadReference=self.name())
        return self

    @undo_chunk("hlibReferenceUnload")
    def unload(self):
        """参照をアンロードする。

        Returns:
            Reference: 自身。

        Raises:
            RuntimeError: Maya がアンロードを拒否した場合。
        """
        cmds.file(unloadReference=self.name())
        return self

    @undo_chunk("hlibReferenceRemove")
    def remove(self):
        """参照を削除する(参照ノードとその内容をシーンから除去する)。

        呼び出し後、このオブジェクトが参照していたノードはシーン上に存在しなくなる。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: Maya が削除を拒否した場合。
        """
        cmds.file(removeReference=True, referenceNode=self.name())
