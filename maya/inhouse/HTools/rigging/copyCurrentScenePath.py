import maya.cmds as cmds

try:
    from PySide2.QtWidgets import QApplication
except ImportError:
    from PySide6.QtWidgets import QApplication


def copy_current_scene_path():
    scene_path = cmds.file(q=True, sn=True)
    if not scene_path:
        cmds.warning("シーンが未保存のため、パスがありません。")
        return

    app = QApplication.instance()
    if app is None:
        cmds.warning("QApplication が取得できません。")
        return

    app.clipboard().setText(scene_path)
    print("Copied:", scene_path)

if __name__ == "__main__":
    copy_current_scene_path()