# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Maya の reference ノードを扱う。"""

import maya.api.OpenMaya as om2
import maya.cmds as cmds
from ..decorator import undoChunk
from .node import Node
from mlib.common.namespace import Namespace



class Reference(Node):
    """Maya の reference ノードラッパー。参照ファイルの照会・ロード制御を提供する。"""
    def mfn(self) -> om2.MFnReference:
        """この reference ノードで最も具体的な om2 function set を取得する。

        呼び出すたびに新しい ``om2.MFnReference`` を保持するノードから作る。

        Returns:
            om2.MFnReference: この reference ノードの function set。
        """
        ...
    def getFilename(self, resolved: bool = ..., withCopyNumber: bool = ...) -> str:
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
        ...
    def getAssociatedNamespace(self) -> Namespace:
        """参照内容が読み込まれている Namespace を取得する。

        Returns:
            Namespace: 参照の名前空間。
        """
        ...
    def isLoaded(self) -> bool:
        """参照が現在ロードされているか判定する。

        Returns:
            bool: ロード済みなら True。
        """
        ...
    def getNodes(self) -> list[Node]:
        """この参照が持ち込んだノードを取得する。

        Returns:
            list[Node]: 参照内のノードラッパー。

        Raises:
            RuntimeError: 参照が現在アンロードされている場合。
        """
        ...
    def getParentReference(self) -> Reference | None:
        """親の Reference を取得する(ネストした参照の場合)。

        Returns:
            Reference | None: 親参照。トップレベルの参照では None。
            ファイルを持たない参照ノード(createNode で作ったもの等。MFnReference.parentReference
            が失敗する)も None。
        """
        ...
    def getChildren(self) -> list[Reference]:
        """自身を親に持つ、直下にネストした子 Reference を取得する。

        Returns:
            list[Reference]: 子参照。無ければ空リスト。孫以下は含めない。
        """
        ...
    def getRoot(self) -> Reference:
        """ネストの最上位(トップレベル)の Reference を取得する。

        Returns:
            Reference: トップレベルの参照。自身がトップレベルならそのまま自身。
        """
        ...
    def isTopLevel(self) -> bool:
        """トップレベル(親を持たない)の参照か判定する。

        Returns:
            bool: 親参照が無ければ True。
        """
        ...
    def getEditStrings(self, successful: bool = ..., failed: bool = ...) -> list[str]:
        """このReferenceに対するEdit(MELコマンド文字列)一覧を取得する。

        Args:
            successful (bool): 実際に適用された(成功した)Editを含めるか。
            failed (bool): 適用に失敗したEditを含めるか。

        Returns:
            list[str]: Editを表すMELコマンド文字列。無ければ空リスト。
        """
        ...
    def getEditNodeNames(self, successful: bool = ..., failed: bool = ...) -> list[str]:
        """Editの影響を受けたノードのフルパス名一覧を取得する。

        Args:
            successful (bool): 実際に適用された(成功した)Editを含めるか。
            failed (bool): 適用に失敗したEditを含めるか。

        Returns:
            list[str]: Editが加えられたノードのフルパス名(重複あり得る)。無ければ空リスト。
        """
        ...
    def getEditAttrNames(self, successful: bool = ..., failed: bool = ...) -> list[str]:
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
        ...
    def load(self) -> Reference:
        """参照をロードする。

        Returns:
            Reference: 自身。

        Raises:
            RuntimeError: Maya がロードを拒否した場合。
        """
        ...
    def unload(self) -> Reference:
        """参照をアンロードする。

        Returns:
            Reference: 自身。

        Raises:
            RuntimeError: Maya がアンロードを拒否した場合。
        """
        ...
    def remove(self) -> None:
        """参照を削除する(参照ノードとその内容をシーンから除去する)。

        呼び出し後、このオブジェクトが参照していたノードはシーン上に存在しなくなる。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: Maya が削除を拒否した場合。
        """
        ...
