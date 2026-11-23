"""選択オブジェクトの非デフォーマ履歴を削除するユーティリティ。"""

import mlib

def delete_non_deformer_history_on_selection():
    """現在選択に対して bakePartialHistory(prePostDeformers) を実行します。"""
    # コンポーネントを選んでいるときは、元と同じくその持ち主のノードを対象にする。
    objs = mlib.ls(sl=True, objectsOnly=True)

    for obj in objs:
        # デフォーマ履歴を保持しつつ、それ以外の履歴を焼き込む。
        obj.deleteHistory(keepDeformers=True)


if __name__ == "__main__":
    delete_non_deformer_history_on_selection()