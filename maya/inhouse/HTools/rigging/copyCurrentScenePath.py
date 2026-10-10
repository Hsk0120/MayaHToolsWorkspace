"""現在シーンのフルパスをクリップボードへコピーするユーティリティ。"""

import maya.cmds as cmds


try:
    from PySide2.QtWidgets import QApplication
except ImportError:
    from PySide6.QtWidgets import QApplication


def copy_current_scene_path():
    """現在シーンパスを取得してクリップボードへコピーします。"""
    # 未保存のシーンでは空文字が返る。保存済みならスラッシュ区切りの絶対パス。
    scene_path = cmds.file(query=True, sceneName=True) or ''
    if not scene_path:
        cmds.warning("The scene has not been saved, so it has no path.")
        return

    app = QApplication.instance()
    if app is None:
        cmds.warning("Could not get the QApplication.")
        return

    # Maya から取得した絶対パスをそのままコピーする。
    app.clipboard().setText(scene_path)
    print("Copied:", scene_path)

if __name__ == "__main__":
    copy_current_scene_path()