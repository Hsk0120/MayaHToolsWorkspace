GUIイベント監視
===============

``hlib.events`` は Maya GUI の ``scriptJob`` を所有者ごとに管理します。
importだけでは監視を開始しません。バッチでは登録を拒否します。
評価ノードの代替ではなく、アイドル時に設定変更へ応答する用途です。
再生中のフレーム評価には使用しません。

.. code-block:: python

    import hlib

    control = hlib.getNode("settings_ctrl")
    jobs = hlib.events.ScriptJobs()

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

アトリビュートの取得と変更通知の抑制
------------------------------------------------------------

``hlib.getPlug("settings_ctrl.enabled")`` は既存アトリビュートを型に対応するPlugへ解決します。
Plug自身やOpenMaya API 2.0のMPlugも受け付けます。

``Plug.set_if_changed(value, unlock=False)`` はbool/int/float/strのスカラー値を
厳密比較し、異なる場合だけ更新します。更新した場合はTrue、同じならFalseを返します。
``unlock=True`` では一時的にロックを解除し、書込みに失敗した場合もロックを復元します。
接続先への書込みやキーのあるアトリビュートに特別な迂回処理は行いません。
複合値や配列値には ``set()`` を使用してください。
