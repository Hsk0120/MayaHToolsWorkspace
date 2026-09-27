通知と標準出力
==============

出力の入口は ``hlib.utils.logger`` に集約します。

.. code-block:: python

   from hlib.utils import logger

   logger.print("選択数:", 3)
   logger.info("作成しました: %s", "arm")
   logger.debug("入力値: %s", 0.5)
   logger.warning("対象が選択されていません")
   logger.error("読み込めませんでした")

``debug`` / ``info`` / ``warning`` / ``error`` は標準loggingへ出力します。
MayaではScript Editorに表示し、warningとerrorはビューポートにも通知します。
``error`` 自体は例外を送出しません。通知して処理を中断する場合は
``logger.raise_with_notify(ValueError, "入力が不正です")`` を使用します。

``print`` はPython標準のprintと同じ出力です。複数の値、sep・end・file・flushに
対応し、改行や出力先を変更できます。ログレベルやビューポート通知は付きません。
標準出力の差替えも尊重し、Mayaでは通常Script Editorに表示されます。

``hlib.cmds.warning`` と ``hlib.warning`` は廃止しました。
使用側は ``logger.warning`` に更新してください。互換用ファイルはありません。
``hlib.reload()`` 後も共有ロガーのMayaハンドラを重複登録しません。
