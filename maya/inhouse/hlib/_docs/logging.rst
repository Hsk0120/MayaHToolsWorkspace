通知と標準出力
==============

出力の入口は ``hlib.logger`` に集約します。

.. code-block:: python

   from hlib import logger

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

失敗理由を確認する
------------------

``exc_info=True`` を渡すと、Script Editorに例外の型・メッセージ・トレースを
表示します。ビューポートにはログ本文だけを表示するため、詳細が画面を覆いません。
``stack_info=True`` と標準loggingのFormatterもScript Editor側へ適用します。

.. code-block:: python

   try:
       raise ValueError("対象の頂点番号が不正です")
   except ValueError:
       logger.error("デルタを読み込めませんでした", exc_info=True)

表示書式は標準loggingのハンドラで設定できます。MayaハンドラのFormatterは
Script Editorへ適用し、ビューポートのメッセージ本文は変更しません。
Formatterの必須項目がログにないなどの書式エラーは、標準書式と失敗理由を
Script Editorへ表示します。書式設定の失敗で呼出元の例外や後続の復元処理を止めません。

.. code-block:: python

   import logging
   from hlib.logger import MayaHandler, get_logger

   for handler in get_logger().handlers:
       if isinstance(handler, MayaHandler):
           handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

``preservedSkinShape`` はスキン保護のモード照会・切替・再キャッシュ・復元に
失敗した場合、対象skinClusterと処理段階を警告します。従来どおりRuntimeErrorは
抑制し、with本体の例外は維持します。警告があれば保護・復元が完了したとは限りません。
