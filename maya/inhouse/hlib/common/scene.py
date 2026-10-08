"""現在の Maya シーンの状態確認とファイル操作を提供する。"""

from pathlib import Path

import maya.cmds as cmds

from .._core.flags import flag_aliases
from .._core.getterAlias import _getter_alias


class Scene:
    """取得時のシーンパスを保持するオブジェクト。生成だけではシーンを開かない。"""

    _FILE_TYPES = {
        ".ma": "mayaAscii",
        ".mb": "mayaBinary",
    }

    def __init__(self, path=None):
        """指定パス、または現在のシーンパスを保持する。

        Args:
            path (str | Path | None): None は現在のシーン。存在確認や読み込みはしない。

        Returns:
            None: 値を返さない。
        """
        self._path = self._current_path() if path is None else self._path_arg(path).resolve()

    def __repr__(self):
        """保持するシーンパスを含むデバッグ表現を返す。

        Returns:
            str: 保持するパスを含む文字列表現。
        """
        return f"Scene(path={self.path!r})"

    def __str__(self):
        """保持パスを表示する。未保存の場合は untitled。"""
        return str(self._path) if self._path is not None else "untitled"

    @property
    def path(self):
        """保持している絶対パスを返す。

        Returns:
            Path | None: 未保存シーンとして取得した場合は None。
        """
        return self._path

    @property
    def name(self):
        """保持パスのファイル名を返す。

        Returns:
            str | None: ファイル名。未保存の場合は ``None``。
        """
        scene_path = self.path
        return scene_path.name if scene_path is not None else None

    def isCurrent(self):
        """保持パスが現在のシーンと一致するか返す。未保存同士は一致とする。"""
        return self.path == self._current_path()

    def isNew(self):
        """保持パスが未保存シーンを表すか判定する。

        Returns:
            bool: このインスタンスが保持するパスがない場合は True。
        """
        return self.path is None

    def isModified(self):
        """現在のシーンに未保存の変更があるか判定する。

        Returns:
            bool: Maya の modified フラグが有効なら True。

        Raises:
            RuntimeError: 保持パスが現在のシーンと一致しない場合。
        """
        self._require_current()
        return bool(cmds.file(query=True, modified=True))

    def getFileType(self):
        """現在のシーンは Maya に照会し、それ以外は保持パスの拡張子から形式を返す。

        Returns:
            str | None: Mayaのファイル形式名。未保存または未取得の場合は ``None``。
        """
        if not self.isCurrent():
            return self._FILE_TYPES.get(self.path.suffix.lower()) if self.path else None
        file_types = cmds.file(query=True, type=True) or []
        return file_types[0] if file_types else None

    @flag_aliases(f="force")
    def new(self, force=False, prompt=True):
        """新規シーンを作成する。

        Args:
            force (bool): ``True`` の場合は未保存変更を破棄する。 別名 ``f`` も使用可能。
            prompt (bool): ``True`` の場合はMayaの確認を許可する。

        Returns:
            Scene: 自身。
        """
        cmds.file(new=True, force=force, prompt=prompt)
        self._path = self._current_path()
        return self

    @flag_aliases(f="force")
    def open(self, path=None, force=False, prompt=True, ignore_version=False):
        """指定したMayaシーンを開く。

        Args:
            path (str | Path | None): 開くパス。省略時は保持しているパス。
            force (bool): ``True`` の場合は未保存変更を破棄する。 別名 ``f`` も使用可能。
            prompt (bool): ``True`` の場合はMayaの確認を許可する。
            ignore_version (bool): ``True`` の場合はMayaバージョン確認を無視する。

        Returns:
            Scene: 自身。

        Raises:
            ValueError: path が空文字列または str/Path 以外の場合。
            RuntimeError: Maya がファイルを開けない場合。
        """
        scene_path = self._path_arg(self.path if path is None else path)
        cmds.file(
            str(scene_path),
            open=True,
            force=force,
            prompt=prompt,
            ignoreVersion=ignore_version,
        )
        self._path = self._current_path()
        return self

    @flag_aliases(f="force")
    def save(self, force=False, fileType=None):
        """現在のシーンを保存する。

        Args:
            force (bool): ``True`` の場合は既存ファイルを上書きする。 別名 ``f`` も使用可能。
            fileType (str | None): Mayaのファイル形式。省略時は現在の形式を使う。

        Returns:
            Scene: 自身。

        Raises:
            RuntimeError: 現在のシーンと一致しない、または保存先がない場合。
        """
        self._require_current()
        if self.isNew():
            raise RuntimeError("Cannot save an untitled scene without a path")
        kwargs = {"save": True, "force": force}
        if fileType is not None:
            kwargs["type"] = fileType
        cmds.file(**kwargs)
        return self

    @flag_aliases(f="force")
    def saveAs(self, path, force=False, fileType=None):
        """指定したパスへ現在のシーンを保存する。

        保存前に現在のシーン名を変更する。保存失敗時も元のシーン名へ戻さない。保存先ディレクトリは作成しない。

        Args:
            path (str | Path): 保存先のシーンファイルパス。
            force (bool): ``True`` の場合は既存ファイルを上書きする。 別名 ``f`` も使用可能。
            fileType (str | None): Mayaのファイル形式。省略時は拡張子から推測する。

        Returns:
            Scene: 自身。

        Raises:
            ValueError: path が不正、または fileType が未指定で拡張子が .ma/.mb 以外の場合。
            RuntimeError: 現在のシーンと一致しない、または Maya が保存できない場合。
        """
        self._require_current()
        scene_path = self._path_arg(path)
        resolved_type = fileType or self._file_type_for(scene_path)
        cmds.file(rename=str(scene_path))
        self._path = self._current_path()
        kwargs = {"save": True, "force": force, "type": resolved_type}
        cmds.file(**kwargs)
        return self

    def importFile(self, path, namespace=None, preserve_references=False):
        """他のシーンファイルの内容を現在のシーンへインポートする。

        インポート先は常に現在のシーンであり、保持パス(self)自体は変化しない。

        Args:
            path (str | Path): インポートするファイルのパス。
            namespace (str | None): インポートしたノードに付ける名前空間。
                省略時はMayaの既定(ファイル名ベース)を使う。
            preserve_references (bool): ``True`` の場合、インポート元が持つ
                参照を参照のまま維持する。``False`` の場合は参照先ノードも実体化する。

        Returns:
            list[Node]: インポートによって新規に作成されたノード。

        Raises:
            ValueError: path が不正な場合。
            RuntimeError: 保持パスが現在のシーンと一致しない、または Maya がインポートに失敗した場合。
        """
        self._require_current()
        from ..nodes.node import Node

        scene_path = self._path_arg(path)
        kwargs = {"returnNewNodes": True, "preserveReferences": preserve_references}
        kwargs["import"] = True
        if namespace is not None:
            kwargs["namespace"] = namespace
        new_names = cmds.file(str(scene_path), **kwargs) or []
        return [Node(name) for name in new_names]

    @_getter_alias(getFileType)
    def fileType(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getFileType(*args, **kwargs)

    @staticmethod
    def _current_path():
        """現在のシーンの絶対パスを返す。未保存なら None。"""
        value = cmds.file(query=True, sceneName=True)
        return Path(value).resolve() if value else None

    def _require_current(self):
        """現在のシーンと一致しない場合は RuntimeError を送出する。"""
        if not self.isCurrent():
            raise RuntimeError("Scene is not the current Maya scene; open it first")

    @staticmethod
    def _path_arg(path):
        """Scene操作用のパス引数をPathへ変換する。

        Args:
            path (str | Path): 空でないパス文字列または Path。

        Returns:
            Path: チルダを展開したパス。相対パスの絶対化やファイル存在確認はしない。

        Raises:
            ValueError: 空文字列または str/Path 以外の場合。
        """
        if not isinstance(path, (str, Path)) or not str(path):
            raise ValueError("path must be a non-empty string or Path")
        return Path(path).expanduser()

    @classmethod
    def _file_type_for(cls, path):
        """シーンファイルの拡張子からMayaのファイル形式を推測する。

        Args:
            path (Path): 拡張子を参照するパス。

        Returns:
            str: .ma は mayaAscii、.mb は mayaBinary。拡張子の大文字小文字は区別しない。

        Raises:
            ValueError: .ma/.mb 以外の拡張子の場合。
        """
        fileType = cls._FILE_TYPES.get(path.suffix.lower())
        if fileType is None:
            raise ValueError("path must have a .ma or .mb extension")
        return fileType
