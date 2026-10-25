なぜmlib
========

Mayaの対象を参照として保持し、名前の受渡しと値の計算を整理するためのライブラリです。

* ``Node`` はノード、``Plug`` はアトリビュート、``Component`` は頂点やCVなどを参照します。
* ``Matrix``・``Vector``・``Quaternion`` などの数学型は値を保持し、計算だけではシーンを変更しません。
* 読取りはOpenMayaを基本とし、通常の編集はMayaのUndoに対応します。
  対応する編集の ``fast=True`` はOpenMayaで直接更新し、Undoに記録しません。

.. code-block:: python

   import mlib

   control = mlib.createNode("transform", name="control")
   control.setTranslate((1, 2, 3))
   control.getPlug("visibility").set(True)
   matrix = control.getMatrix(worldSpace=True)

Maya標準のコマンドは ``maya.cmds``、対象の参照と値の操作はmlibを使います。
使い方は :doc:`getting_started`、APIの詳細は :doc:`modules` を参照してください。
