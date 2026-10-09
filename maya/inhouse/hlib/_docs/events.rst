GUIイベント監視
===============

``hlib.common`` は Maya GUI の ``scriptJob`` を所有者ごとに管理します。
importだけでは監視を開始しません。バッチでは登録を拒否します。
評価ノードの代替ではなく、アイドル時に設定変更へ応答する用途です。
再生中のフレーム評価には使用しません。

.. code-block:: python

    import hlib

    control = hlib.node("settings_ctrl")
    jobs = hlib.common.ScriptJobs()

    def changed():
        print(control.plug("enabled").get())

    job = jobs.add(
        "enabled",
        attribute=control.plug("enabled"),
        callback=changed,
        kill_with_scene=True,
        compress_undo=True,
    )
    print(job.id, job.exists())
    jobs.stop()

``ScriptJobs.add()`` は同じキーの監視が生存していればその参照を返します。
その場合、新しいオプションは適用しません。設定を変更する場合は対象の
``ScriptJob.stop()`` を呼んでから追加してください。
``ScriptJobs.exists()`` は空でなく全監視が生存する場合にTrueです。

``event="SelectionChanged"`` などのイベント名も指定できます。
``event`` と ``attribute`` はどちらか一方だけを指定します。
シーンをクリアすると ``kill_with_scene=True`` の監視は解除されます。
再登録のタイミングや対象の再探索は利用側の責務です。

解除は所有する監視だけに作用します。ガベージコレクションでは解除しないため、
ツール終了時には明示的に ``stop()`` を呼びます。hlibの再読込でも既存の所有参照は
保持されますが、利用側のモジュールを再読込する場合は旧コールバックを明示的に解除してください。

一時的に監視する
----------------

``ScriptJobs.temporary()`` はブロック終了時にそのグループの監視を解除します。
対象ノード・UI・シーンの寿命は所有せず、削除しません。
ブロック開始前からグループに保持していた監視も解除対象になります。

.. code-block:: python

    jobs = hlib.common.ScriptJobs()
    with jobs.temporary() as active:
        active.add(
            "selection", event="SelectionChanged",
            callback=lambda: hlib.logger.print(hlib.ls(sl=True)),
        )
        # GUIで処理を行う間だけ監視する。

同じグループのtemporaryを入れ子にすると、内側の開始時にRuntimeErrorを送出します。
内側が外側の監視を解除することはありません。異なるグループなら入れ子にできます。
GCによる解除や新規監視の自動登録は行いません。

解除は全件試み、失敗した監視は通知して保持します。後から ``jobs.stop()`` で再試行できます。
本体が正常終了した場合、解除失敗はRuntimeErrorになります。
本体が既に例外を送出していた場合、その例外を解除失敗で置き換えません。

アトリビュートの取得と変更通知の抑制
------------------------------------------------------------

``hlib.plug("settings_ctrl.enabled")`` は既存アトリビュートを型に対応するPlugへ解決します。
Plug自身やOpenMaya API 2.0のMPlugも受け付けます。

``Plug.setIfChanged(value, unlock=False)`` はbool/int/float/strのスカラー値を
厳密比較し、異なる場合だけ更新します。更新した場合はTrue、同じならFalseを返します。
``unlock=True`` では一時的にロックを解除し、書込みに失敗した場合もロックを復元します。
接続先への書込みやキーのあるアトリビュートに特別な迂回処理は行いません。
複合値や配列値には ``set()`` を使用してください。
