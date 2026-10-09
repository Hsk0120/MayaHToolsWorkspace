タイムスライダーと表示エディタ
============================================================

タイムスライダー・ビューポート・アウトライナーを扱います。

例は Maya の Script Editor で実行します。既存ノード名は使用するシーンに合わせてください。
最初に ``import hlib`` を実行してください。

タイムスライダー・ビューポート・アウトライナー
----------------------------------------------

.. code-block:: python

    import hlib
    hlib.reload()

    slider = hlib.timeSlider()  # hlib.common.TimeSlider
    print(slider.currentTime(), slider.playbackRange())
    slider.setPlaybackRange(1, 120)
    with slider.preserveTime():
        slider.setCurrentTime(24)
    print(slider.selectedRange())  # 未選択はNone。選択範囲の終端は含まない

    view = hlib.viewport()  # hlib.common.Viewport
    print(view.panel, view.camera())
    with view.temporarySettings(grid=False, joints=False):
        pass  # 終了時に指定した表示設定を復元
    with view.suspend():
        pass  # 重い処理。例外時もメインペインの表示状態を復元

    outliner = hlib.outliner()  # hlib.common.Outliner
    outliner.setSettings(showShapes=True, showNamespace=True)
    outliner.expandAll()       # 展開
    outliner.expandAll(False)  # 折りたたむ

``Viewport.suspend()`` はmGearの ``viewportOff`` と同様に、メインペインの
``manage`` を一時的に無効化します。計算・再生を停止する機能ではありません。
メインペイン内のアウトライナー等も対象となり、切り離したウィンドウは対象外です。
元から非表示の場合は非表示へ戻り、ネストと例外にも対応します。
手動切替には ``Viewport.setEnabled(False/True)``、照会には ``enabled()`` を使います。

表示設定はMayaの長いフラグ名で指定します。``settings()`` は対応する表示設定のみを
返し、UI全体やカメラ・階層展開状態は保存しません。
対象を明示する場合は ``hlib.viewport("modelPanel4")``、
``hlib.outliner("outlinerPanel1")`` のように指定します。UIの自動作成は行いません。
ビューポート・アウトライナー・スライダー選択範囲にはMaya GUIが必要です。
時刻・再生範囲の操作はバッチでも利用できます。

参照: `modelEditor <https://help.autodesk.com/cloudhelp/2026/ENU/Maya-Tech-Docs/CommandsPython/modelEditor.html>`_、
`outlinerEditor <https://help.autodesk.com/cloudhelp/2026/ENU/Maya-Tech-Docs/CommandsPython/outlinerEditor.html>`_、
`timeControl <https://help.autodesk.com/cloudhelp/2024/ENU/Maya-Tech-Docs/CommandsPython/timeControl.html>`_。

ChannelBoxと選択状態の操作は :doc:`selection_and_channelbox` を参照してください。

処理中の画面停止
----------------

``hlib.bakeResults()`` はGUIでのベイク中、自動でメインペインを非表示にします。
正常終了・例外のどちらでも元の表示状態へ戻します。
ベイク以外のツールには ``viewportOff()`` をデコレーターまたはコンテキストとして使えます。

.. code-block:: python

    from hlib.decorator import viewportOff

    @viewportOff()
    def build_animation():
        hlib.bakeResults("pCube1", time=(1, 120), attribute="translateX")

    with viewportOff():
        build_animation()

括弧付きの ``@viewportOff()`` を使用します。入れ子でも途中で表示は戻りません。
バッチ実行では表示操作を省略し、ブロックの処理だけ実行します。
OGS・refresh・評価設定は変更しません。例外時に処理を自動再実行することもありません。
