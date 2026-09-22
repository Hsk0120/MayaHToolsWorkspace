"""現在の Maya シーンの状態確認とファイル操作を提供する。"""

from pathlib import Path

import maya.cmds as cmds


class Scene:
    """現在のMayaシーンとシーンファイルを扱うステートレスなFacade。"""

    _FILE_TYPES = {
        ".ma": "mayaAscii",
        ".mb": "mayaBinary",
    }

    def path(self):
        """現在のシーンファイルの絶対パスを返す。

        Returns:
            Path | None: 保存済みシーンのパス。未保存の場合は ``None``。
        """
        scene_path = cmds.file(query=True, sceneName=True)
        return Path(scene_path) if scene_path else None

    def name(self):
        """現在のシーンファイル名を返す。

        Returns:
            str | None: ファイル名。未保存の場合は ``None``。
        """
        scene_path = self.path()
        return scene_path.name if scene_path is not None else None

    def is_new(self):
        """現在のシーンが未保存の新規シーンか判定する。

        Returns:
            bool: 現在のシーンにパスがない場合は True。
        """
        return self.path() is None

    def is_modified(self):
        """現在のシーンに未保存の変更があるか判定する。

        Returns:
            bool: Maya の modified フラグが有効なら True。
        """
        return bool(cmds.file(query=True, modified=True))

    def file_type(self):
        """現在のシーンファイル形式を返す。

        Returns:
            str | None: Mayaのファイル形式名。未保存または未取得の場合は ``None``。
        """
        file_types = cmds.file(query=True, type=True) or []
        return file_types[0] if file_types else None

    def new(self, force=False, prompt=True):
        """新規シーンを作成する。

        Args:
            force (bool): ``True`` の場合は未保存変更を破棄する。
            prompt (bool): ``True`` の場合はMayaの確認を許可する。

        Returns:
            Scene: 自身。
        """
        cmds.file(new=True, force=force, prompt=prompt)
        return self

    def open(self, path, force=False, prompt=True, ignore_version=False):
        """指定したMayaシーンを開く。

        Args:
            path (str | Path): 開くシーンファイルのパス。
            force (bool): ``True`` の場合は未保存変更を破棄する。
            prompt (bool): ``True`` の場合はMayaの確認を許可する。
            ignore_version (bool): ``True`` の場合はMayaバージョン確認を無視する。

        Returns:
            Scene: 自身。

        Raises:
            ValueError: path が空文字列または str/Path 以外の場合。
            RuntimeError: Maya がファイルを開けない場合。
        """
        scene_path = self._path_arg(path)
        cmds.file(
            str(scene_path),
            open=True,
            force=force,
            prompt=prompt,
            ignoreVersion=ignore_version,
        )
        return self

    def save(self, force=False, file_type=None):
        """現在のシーンを保存する。

        Args:
            force (bool): ``True`` の場合は既存ファイルを上書きする。
            file_type (str | None): Mayaのファイル形式。省略時は現在の形式を使う。

        Returns:
            Scene: 自身。

        Raises:
            RuntimeError: シーンが未保存で保存先がない場合。
        """
        if self.is_new():
            raise RuntimeError("Cannot save an untitled scene without a path")
        kwargs = {"save": True, "force": force}
        if file_type is not None:
            kwargs["type"] = file_type
        cmds.file(**kwargs)
        return self

    def save_as(self, path, force=False, file_type=None):
        """指定したパスへ現在のシーンを保存する。

        保存前に現在のシーン名を変更する。保存失敗時も元のシーン名へ戻さない。保存先ディレクトリは作成しない。

        Args:
            path (str | Path): 保存先のシーンファイルパス。
            force (bool): ``True`` の場合は既存ファイルを上書きする。
            file_type (str | None): Mayaのファイル形式。省略時は拡張子から推測する。

        Returns:
            Scene: 自身。

        Raises:
            ValueError: path が不正、または file_type が未指定で拡張子が .ma/.mb 以外の場合。
            RuntimeError: Maya がファイルを保存できない場合。
        """
        scene_path = self._path_arg(path)
        resolved_type = file_type or self._file_type_for(scene_path)
        cmds.file(rename=str(scene_path))
        kwargs = {"save": True, "force": force, "type": resolved_type}
        cmds.file(**kwargs)
        return self

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
        file_type = cls._FILE_TYPES.get(path.suffix.lower())
        if file_type is None:
            raise ValueError("path must have a .ma or .mb extension")
        return file_type

    def __repr__(self):
        """現在のシーンパスを含むデバッグ表現を返す。

        Returns:
            str: 現在のパスを含む文字列表現。
        """
        return f"Scene(path={self.path()!r})"
