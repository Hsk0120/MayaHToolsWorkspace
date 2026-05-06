"""選択オブジェクトの非デフォーマ履歴を削除するユーティリティ。"""

import maya.cmds as cmds

def delete_non_deformer_history_on_selection():
    """現在選択に対して bakePartialHistory(prePostDeformers) を実行します。"""
    objs = cmds.ls(sl=True)

    for obj in objs:
        # デフォーマ履歴を保持しつつ、それ以外の履歴を焼き込む。
        cmds.bakePartialHistory(obj, prePostDeformers=True)


if __name__ == "__main__":
    delete_non_deformer_history_on_selection()