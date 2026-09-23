"""Maya の現在のワークスペース(プロジェクト)を扱う。"""

from pathlib import Path

import maya.cmds as cmds


class Workspace:
    """Maya の現在のワークスペース(プロジェクト)を参照・変更する。

    Maya のワークスペースはセッションに1つだけ存在するグローバルな状態のため、
    このクラスはインスタンスを持たず、常に現在のワークスペースを対象にする。
    """

    @staticmethod
    def root():
        """現在のワークスペースのルートディレクトリを取得する。

        Returns:
            Path: ルートディレクトリの絶対パス。
        """
        return Path(cmds.workspace(query=True, rootDirectory=True))

    @staticmethod
    def open(path):
        """指定したディレクトリを現在のワークスペースとして開く。

        Args:
            path (str | Path): ワークスペースのルートにする既存のディレクトリ。

        Returns:
            None: 値を返さない。

        Raises:
            ValueError: path が空、または str/Path 以外の場合。
            RuntimeError: Maya が開けない場合(存在しないパスなど)。
        """
        if not isinstance(path, (str, Path)) or not str(path):
            raise ValueError("path must be a non-empty string or Path")
        cmds.workspace(str(path), openWorkspace=True)

    @staticmethod
    def rule(name):
        """指定したファイルルールのサブディレクトリを取得する。

        Args:
            name (str): ワークスペースのファイルルール名(例: ``"scene"``、
                ``"sourceImages"``)。

        Returns:
            str: ルートからの相対パス。未設定のルール名では空文字列。
        """
        return cmds.workspace(fileRuleEntry=name)

    @staticmethod
    def set_rule(name, path):
        """ファイルルールのサブディレクトリを設定する。

        Args:
            name (str): ワークスペースのファイルルール名。
            path (str): ルートからの相対パス。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: Maya が設定を拒否した場合。
        """
        cmds.workspace(fileRule=(name, str(path)))

    @staticmethod
    def rules():
        """定義済みのファイルルール名の一覧を取得する。

        Returns:
            list[str]: ファイルルール名の一覧。
        """
        return cmds.workspace(query=True, fileRuleList=True) or []

    @staticmethod
    def expand(name):
        """ワークスペースルートを基準に相対パスを絶対パスへ展開する。

        ``name`` はそのままルートへ連結される文字列として扱われ、
        ファイルルール名としては解決されない(例: ``"scene"`` は
        ``rule("scene")`` が返す ``"scenes"`` には解決されず、文字通り
        ``<root>/scene`` になる)。ルールが指すディレクトリを取得する場合は
        ``path_for`` を使う。

        Args:
            name (str): 展開する相対パスまたはファイル名。

        Returns:
            Path: 展開結果の絶対パス。
        """
        return Path(cmds.workspace(expandName=name))

    @staticmethod
    def path_for(rule_name, filename=""):
        """指定したファイルルールのディレクトリを絶対パスで取得する。

        Args:
            rule_name (str): ワークスペースのファイルルール名(例: ``"scene"``)。
            filename (str): ルールディレクトリ内のファイル名。省略時はディレクトリ自体。

        Returns:
            Path: 絶対パス。
        """
        relative = Workspace.rule(rule_name)
        base = Workspace.root() / relative if relative else Workspace.root()
        return base / filename if filename else base
