Maya標準UIとの併用
==================

UIの作成・参照・標準エディターの起動は、利用側でMaya標準のcmds/melを使います。
mlibはUIオブジェクト、ドッキング状態、ShelfやEditor設定の保存を提供しません。
Qtウィジェットの取得・変換も利用側のUIパッケージが担当します。

.. code-block:: python

   import maya.cmds as cmds
   import maya.mel as mel

   if not cmds.about(batch=True):
       main_window = mel.eval("$tmp = $gMainWindow")
       mel.eval("NodeEditorWindow;")
       mel.eval("GraphEditor;")

画面を一時的に非表示にする
----------------------------------------

重いシーン更新中は、既存の ``mlib.decorator.viewportOff`` を使えます。
例外時にも元の表示状態を復元し、入れ子では外側の非表示を維持します。

.. code-block:: python

   from mlib.decorator import viewportOff

   with viewportOff():
       # シーン更新を行う。
       pass

バッチでは表示状態を変更しません。処理中にGUIが削除された場合も再作成しません。
このコンテキストはUndoやシーン全体の評価モードを変更しません。
