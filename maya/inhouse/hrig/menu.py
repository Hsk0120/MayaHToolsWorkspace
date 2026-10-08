"""Maya上部のhrig実行メニュー。"""

from maya import cmds

from functools import partial
import hlib
from hlib.common import MainWindow


class Menu:
    """仮の作成・編集メニューを同一セッションで一つだけ管理する。"""

    NAME = "hrigMainMenu"

    @classmethod
    def install(cls):
        """GUIのメインメニューバーへ登録する。既存なら再利用する。

        Returns:
            str | None: メニュー名。バッチではNone。
        """
        if cmds.about(batch=True):
            return None
        if cmds.menu(cls.NAME, exists=True):
            return cls.NAME
        parent = MainWindow.getName()
        cmds.menu(cls.NAME, label="hrig", parent=parent, tearOff=True)
        cmds.menuItem(
            label="レイヤーエディタを開く", parent=cls.NAME, command=partial(cls.run, "editor")
        )
        create = cmds.menuItem(label="サンプル作成", parent=cls.NAME, subMenu=True, tearOff=True)
        for kind, label in (
            ("limb", "腕・脚 FK / IK"),
            ("demo", "メッシュ付き腕・脚"),
            ("finger", "指 Curl / Spread"),
            ("aim", "首・視線 Aim"),
            ("spine", "背骨 Spline IK"),
            ("tail", "尻尾 Spline IK"),
            ("skirt", "スカート 4方向"),
        ):
            cmds.menuItem(label=label, parent=create, command=partial(cls.run, kind))
        cmds.menuItem(divider=True, parent=cls.NAME)
        cmds.menuItem(
            label="選択スカートのポーズ補正を編集",
            parent=cls.NAME,
            command=partial(cls.run, "pose"),
        )
        cmds.menuItem(
            label="選択骨へ局所Tweakを追加", parent=cls.NAME, command=partial(cls.run, "tweak")
        )
        return cls.NAME

    @staticmethod
    def selected_rig():
        """選択ノードの祖先からモジュールを解決する。

        Returns:
            tuple: モジュールと元の選択ノード名。

        Raises:
            ValueError: 選択がモジュールに所属しない場合。
        """
        from .moduleRegistry import ModuleRegistry

        selected = [item.getFullName() for item in hlib.ls(selection=True, long=True)] or []
        if not selected:
            raise ValueError("hrigのモジュールまたは配下のノードを選択してください")
        for root in ModuleRegistry.roots():
            rig = ModuleRegistry.get(root)
            path = rig.root.getFullName()
            if selected[0] == path or selected[0].startswith(path + "|"):
                return rig, selected[0]
        raise ValueError("選択ノードはhrigモジュールに所属していません")

    @classmethod
    def run(cls, action, *unused):
        """メニューを実行し、構築したモジュールをレイヤーUIへ表示する。

        Args:
            action (str): メニュー操作ID。
            *unused: Maya UIコールバックの引数。

        Returns:
            object | None: 作成結果。失敗時はMayaへ警告を表示。
        """
        from . import show_layer_editor, build_spline, build_skirt
        from .sampleBuilder import SampleBuilder

        try:
            if action == "editor":
                return show_layer_editor()
            if action == "pose":
                from .skirtRig import SkirtRig

                rig, _ = cls.selected_rig()
                if not isinstance(rig, SkirtRig):
                    raise ValueError("スカートモジュールを選択してください")
                from .poseEditor import PoseEditor

                editor = show_layer_editor()
                editor._pose_editor = PoseEditor(rig, parent=editor)
                editor._pose_editor.show()
                return editor._pose_editor
            if action == "tweak":
                from .tweakLayer import TweakLayer

                rig, joint = cls.selected_rig()
                layer = TweakLayer(rig)
                return layer.add(SampleBuilder.next_id(set(layer.groups()), "tweak"), joint)
            name = SampleBuilder.next_id(set([item.getName() for item in hlib.ls()]), action)
            if action in ("limb", "demo"):
                rig = SampleBuilder.module(name, demo=action == "demo")
            elif action in ("spine", "tail"):
                rig = build_spline(name, axis="y" if action == "spine" else "z")
            elif action == "skirt":
                rig = build_skirt(name)
            elif action == "finger":
                from .fingerRig import FingerRig

                rig = FingerRig.create(name)
            elif action == "aim":
                from .aimRig import AimRig

                rig = AimRig.create(name)
            else:
                raise ValueError("Unknown menu action")

            hlib.select(rig.root, replace=True)
            editor = show_layer_editor()
            editor.refresh()
            from .layerEditor import QtCore

            for row in editor.rows():
                data = row.data(0, QtCore.Qt.UserRole)
                if data["root"] == rig.root.getUuid() and data["role"] == "module":
                    editor.tree.setCurrentItem(row)
                    break
            return rig
        except Exception as error:
            hlib.logger.warning("hrig: " + str(error))
            return None

    @classmethod
    def remove(cls):
        """自身のメニューだけを削除する。"""
        if not cmds.about(batch=True) and cmds.menu(cls.NAME, exists=True):
            cmds.deleteUI(cls.NAME, menu=True)
