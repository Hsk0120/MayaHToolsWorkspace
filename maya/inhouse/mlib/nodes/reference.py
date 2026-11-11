"""Maya の reference ノードを扱う。"""

import os
import re

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from ..decorator import _require_bool, undoChunk
from .node import Node


class Reference(Node):
    """Maya の reference ノードラッパー。参照ファイルの照会・ロード制御を提供する。"""

    def mfn(self):
        """この reference ノードで最も具体的な om2 function set を取得する。

        呼び出すたびに新しい ``om2.MFnReference`` を保持するノードから作る。

        Returns:
            om2.MFnReference: この reference ノードの function set。
        """
        return om2.MFnReference(self.mnode())

    def getFilename(self, resolved=True, withCopyNumber=False):
        """参照ファイルのパスを取得する。

        Args:
            resolved (bool): True の場合、パス変数などを解決した実際のパスを返す。
                False の場合はシーンに保存されている未解決のパスを返す。
            withCopyNumber (bool): True の場合、同じファイルを複数回参照した
                際のコピー番号(``{1}`` 等)を含める。最初の参照には番号が付かない。
                ``cmds.referenceQuery(ref, filename=True)`` と同じ値になる。

        Returns:
            str: 参照ファイルのパス(常にディレクトリを含む)。
        """
        # MFnReference.fileName の2番目はパスを除く指定(Falseでディレクトリを含む)、
        # 3番目がコピー番号を含める指定。
        return self.mfn().fileName(resolved, False, withCopyNumber)

    def getAssociatedNamespace(self):
        """参照内容が読み込まれている Namespace を取得する。

        Returns:
            Namespace: 参照の名前空間。
        """
        # common.namespaceの初期化順に依存しないよう、
        # mlib 内の他の相互依存箇所と合わせて遅延 import で統一する。
        from ..common import Namespace

        return Namespace(self.mfn().associatedNamespace(False))

    def getCopyNumber(self):
        """同じファイルを複数回リファレンスした際のコピー番号を取得する。

        :meth:`getFilename` の ``withCopyNumber=True`` の末尾 ``{N}`` の番号。

        Returns:
            int: コピー番号。番号の付かない最初のリファレンスでは 0。
        """
        match = re.search(r"\{(\d+)\}$", self.getFilename(withCopyNumber=True))
        return int(match.group(1)) if match else 0

    def isUsingNamespaces(self):
        """リファレンスの内容が名前空間で読み込まれているか(古い接頭辞の方式でないか)を判定する。

        Returns:
            bool: ``cmds.file(..., query=True, usingNamespaces=True)`` の結果。
        """
        return bool(cmds.file(self.getFilename(withCopyNumber=True), query=True, usingNamespaces=True))

    def isDeferred(self):
        """シーンを開いた際にロードを保留する(``cmds.file(deferReference=True)``)設定か判定する。

        Returns:
            bool: ``cmds.file(..., query=True, deferReference=True)`` の結果。
        """
        return bool(cmds.file(self.getFilename(withCopyNumber=True), query=True, deferReference=True))

    def isLoaded(self):
        """参照が現在ロードされているか判定する。

        Returns:
            bool: ロード済みなら True。
        """
        return self.mfn().isLoaded()

    def getNodes(self):
        """この参照が持ち込んだノードを取得する。

        Returns:
            list[Node]: 参照内のノードラッパー。

        Raises:
            RuntimeError: 参照が現在アンロードされている場合。
        """
        if not self.isLoaded():
            raise RuntimeError("Cannot enumerate nodes of an unloaded reference")
        return [Node(mobject) for mobject in self.mfn().nodes()]

    def getParentReference(self):
        """親の Reference を取得する(ネストした参照の場合)。

        Returns:
            Reference | None: 親参照。トップレベルの参照では None。
            ファイルを持たない参照ノード(createNode で作ったもの等。MFnReference.parentReference
            が失敗する)も None。
        """
        try:
            parent = self.mfn().parentReference()
        except RuntimeError:
            if not self.isValid():
                raise
            return None
        if parent.isNull():
            return None
        return Reference(parent)

    def getChildren(self):
        """自身を親に持つ、直下にネストした子 Reference を取得する。

        Returns:
            list[Reference]: 子参照。無ければ空リスト。孫以下は含めない。
        """
        from ..common.references import listReferences

        own_name = self.getFullName()
        children = []
        for reference in listReferences():
            parent = reference.getParentReference()
            if parent is not None and parent.getFullName() == own_name:
                children.append(reference)
        return children

    def getRoot(self):
        """ネストの最上位(トップレベル)の Reference を取得する。

        Returns:
            Reference: トップレベルの参照。自身がトップレベルならそのまま自身。
        """
        reference = self
        parent = reference.getParentReference()
        while parent is not None:
            reference = parent
            parent = reference.getParentReference()
        return reference

    def isTopLevel(self):
        """トップレベル(親を持たない)の参照か判定する。

        Returns:
            bool: 親参照が無ければ True。
        """
        return self.getParentReference() is None

    def getEditStrings(self, successful=True, failed=False):
        """このReferenceに対するEdit(MELコマンド文字列)一覧を取得する。

        Args:
            successful (bool): 実際に適用された(成功した)Editを含めるか。
            failed (bool): 適用に失敗したEditを含めるか。

        Returns:
            list[str]: Editを表すMELコマンド文字列。無ければ空リスト。
        """
        return cmds.referenceQuery(
            self.getName(), editStrings=True,
            successfulEdits=successful, failedEdits=failed,
        ) or []

    def getEditNodeNames(self, successful=True, failed=False):
        """Editの影響を受けたノードのフルパス名一覧を取得する。

        Args:
            successful (bool): 実際に適用された(成功した)Editを含めるか。
            failed (bool): 適用に失敗したEditを含めるか。

        Returns:
            list[str]: Editが加えられたノードのフルパス名(重複あり得る)。無ければ空リスト。
        """
        return cmds.referenceQuery(
            self.getName(), editNodes=True,
            successfulEdits=successful, failedEdits=failed,
        ) or []

    def getEditAttrNames(self, successful=True, failed=False):
        """Editの影響を受けたアトリビュートの短縮名一覧を取得する。

        Maya の ``referenceQuery -editAttrs`` 自体がノード名を含まないアトリビュート名の
        みを返す(コンパウンドアトリビュートの子を編集した場合は親の短縮名になる)。
        どのノードのアトリビュートかは ``getEditNodeNames()`` や ``getEditStrings()`` と合わせて判断する。

        Args:
            successful (bool): 実際に適用された(成功した)Editを含めるか。
            failed (bool): 適用に失敗したEditを含めるか。

        Returns:
            list[str]: Edit対象のアトリビュートの短縮名(重複あり得る)。無ければ空リスト。
        """
        return cmds.referenceQuery(
            self.getName(), editAttrs=True,
            successfulEdits=successful, failedEdits=failed,
        ) or []

    @undoChunk("mlibReferenceLoad")
    def load(self):
        """参照をロードする。

        Returns:
            Reference: 自身。

        Raises:
            RuntimeError: Maya がロードを拒否した場合。
        """
        cmds.file(loadReference=self.getName())
        return self

    @undoChunk("mlibReferenceUnload")
    def unload(self):
        """参照をアンロードする。

        Returns:
            Reference: 自身。

        Raises:
            RuntimeError: Maya がアンロードを拒否した場合。
        """
        cmds.file(unloadReference=self.getName())
        return self

    @undoChunk("mlibReferenceRemoveEdits")
    def removeEdits(self, successful=True, failed=True, editCommand=None):
        """このReferenceに対するEditを削除する(``cmds.referenceEdit(removeEdits=True)``)。

        Mayaはロード中のリファレンスの適用済み(成功した)Editを削除しないため、ロード中で ``successful=True`` の
        場合はアンロードしてから削除し、再びロードする。ファイル操作のためUndoには記録されない。

        Args:
            successful (bool): 適用済み(成功した)Editを削除するか。既定 True。
            failed (bool): 適用に失敗したEditを削除するか。既定 True。
            editCommand (str | None): 削除するEditのコマンド名(``"setAttr"``・``"connectAttr"``・``"parent"`` 等)。
                Noneは全コマンド。

        Returns:
            Reference: 自身。

        Raises:
            TypeError: successful・failed が bool 以外、または editCommand が文字列・None以外の場合。
            ValueError: editCommand が空文字列の場合。
            RuntimeError: リファレンスノードが無効、または Maya が操作を拒否した場合。
        """
        _require_bool(successful, "successful")
        _require_bool(failed, "failed")
        flags = {"removeEdits": True, "successfulEdits": successful, "failedEdits": failed}
        if editCommand is not None:
            if not isinstance(editCommand, str):
                raise TypeError("editCommand must be a str or None")
            if not editCommand:
                raise ValueError("editCommand must be a non-empty string")
            flags["editCommand"] = editCommand
        self._require_valid("remove edits of")
        name = self.getName()
        reload = successful and self.isLoaded()
        if reload:
            cmds.file(unloadReference=name)
        try:
            cmds.referenceEdit(name, **flags)
        finally:
            if reload:
                cmds.file(loadReference=name)
        return self

    @undoChunk("mlibReferenceReplaceFile")
    def replaceFile(self, path):
        """リファレンスするファイルを別のファイルへ置き換えて読み込む(``cmds.file(path, loadReference=ref)``)。

        名前空間・Editは維持する。ファイル操作のためUndoには記録されない。

        Args:
            path (str | os.PathLike): 新しいファイルのパス。

        Returns:
            Reference: 自身。

        Raises:
            TypeError: path が文字列・PathLike 以外の場合。
            ValueError: path が空の場合。
            RuntimeError: リファレンスノードが無効、ファイルが無い、または Maya が読込みを拒否した場合。
        """
        if not isinstance(path, (str, os.PathLike)):
            raise TypeError("path must be a str or os.PathLike")
        path = os.fspath(path)
        if not path:
            raise ValueError("path must be a non-empty string")
        self._require_valid("replace the file of")
        cmds.file(path.replace("\\", "/"), loadReference=self.getName())
        return self

    def importContents(self, removeNamespace=False):
        """リファレンスの内容をシーンへ読み込み(``cmds.file(importReference=True)``)、リファレンスを解除する。

        呼び出し後、このリファレンスノードはシーンに存在しなくなる。入れ子の子リファレンスは
        リファレンスのまま残る。ファイル操作のためUndoには記録されない。

        Args:
            removeNamespace (bool): True なら読み込んだ名前空間を削除し、内容を親の名前空間へ移す
                (名前が衝突するノードは :meth:`Namespace.remove` と同じく末尾に番号を付ける)。既定 False。

        Returns:
            list[Node]: 読み込んだノード(リファレンスノードは含まない)。

        Raises:
            TypeError: removeNamespace が bool 以外の場合。
            RuntimeError: リファレンスノードが無効、アンロード中、または Maya が操作を拒否した場合。
        """
        _require_bool(removeNamespace, "removeNamespace")
        self._require_valid("import")
        if not self.isLoaded():
            raise RuntimeError("Cannot import an unloaded reference")
        namespace = self.getAssociatedNamespace() if removeNamespace else None
        nodes = [node for node in self.getNodes() if not node.isType("reference")]
        cmds.file(importReference=True, referenceNode=self.getName())
        if namespace is not None and namespace.name != ":" and namespace.exists():
            namespace.remove(namespace.getParent())
        return [node for node in nodes if node.isValid()]

    @undoChunk("mlibReferenceRemove")
    def remove(self):
        """参照を削除する(参照ノードとその内容をシーンから除去する)。

        呼び出し後、このオブジェクトが参照していたノードはシーン上に存在しなくなる。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: Maya が削除を拒否した場合。
        """
        cmds.file(removeReference=True, referenceNode=self.getName())
