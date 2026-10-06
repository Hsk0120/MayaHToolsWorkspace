シェルフとボタン
========================

``Shelf`` と ``ShelfButton`` は現在のMaya GUIへの参照です。
UIの作成・変更・削除はシーンのUndo対象外で、保存済みファイルを自動更新しません。

.. code-block:: python

   import hlib
   from hlib.ui import Shelf

   shelf = hlib.getShelf()  # 現在のタブ。新規作成しない
   print([item.getName() for item in Shelf.list()])
   print([button.getLabel() for button in shelf.getButtons()])

   shelf = hlib.createShelf("MyTools")  # 同名がある場合は例外
   button = shelf.addButton(
       "Selection", "import maya.cmds as cmds; print(cmds.ls(sl=True))",
       annotation="選択ノードを表示", language="python")
   button.setIcon("commandButton.png")
   button.setLabel("Selected")
   button.setCommand('print "Hello";', language="mel")
   shelf.select()

``getButtons()`` はボタンオブジェクトを表示順で返し、区切り線は除外します。
``button.delete()`` はボタンだけを削除し、``shelf.clear()`` はタブ内の全項目を削除します。
標準タブの内容が未ロードの場合は、取得・変更・保存前にMayaの遅延ロードを完了させます。

明示的に保存する
------------------------

.. code-block:: python

   path = shelf.save()  # ユーザーのshelves/shelf_MyTools.melへ保存
   # 別の場所へ書き出す場合（親フォルダーは事前に用意）
   path = shelf.save("D:/maya_tools/shelf_MyTools.mel")

既存ファイルは上書きします。保存先は :doc:`settings_storage` を参照してください。
この操作はタブ内容のファイル保存であり、Mayaのタブ構成全体の保存ではありません。
任意の場所へ書き出しても自動ロード登録はされません。次回起動時のタブ構成の保持は
Maya側のシェルフ管理・保存機能で行います。

Python callable（関数オブジェクト）はMayaのMEL形式へ保存できないため、
addButton/set_commandには文字列を指定します。登録時にコードは実行しません。
既存ボタンに複数言語のコールバックが混在する場合など、Maya標準saveShelfの制限は残ります。

参考: `Maya saveShelf <https://help.autodesk.com/cloudhelp/2026/ENU/Maya-Tech-Docs/CommandsPython/saveShelf.html>`_
