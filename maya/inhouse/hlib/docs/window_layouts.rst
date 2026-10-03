ウィンドウと画面レイアウト
====================================

``Window`` は通常ウィンドウ、``WorkspaceControl`` はドッキングUIの容器、
``WorkspaceLayout`` は画面全体のワークスペースを扱います。
プロジェクトのフォルダーを扱う既存 ``Workspace`` とは別です。
すべて ``hlib.ui`` にあり、参照を作るだけではUIを作成・移動・保存しません。
対象はMaya標準コマンドへ登録されたUIです。任意のQtウィジェットは対象外です。

画面全体の保存と切り替え
------------------------------------

.. code-block:: python

   import hlib
   from hlib.ui import WorkspaceLayout

   layout = hlib.getWorkspaceLayout()  # 現在の配置への参照
   print([item.name() for item in WorkspaceLayout.list()])
   layout.lock()                       # Maya右上の鍵と同じ
   layout.unlock()
   print(layout.get_locked())

   saved = layout.saveAs("MyRiggingLayout")  # 保存し、その配置へ切り替える
   saved.save()                        # 使用中の配置を上書き保存
   hlib.getWorkspaceLayout("MyRiggingLayout").activate()
   # saved.reset()                     # 未保存変更を捨てて保存済み配置へ戻す

ロックは全体のドッキング操作に作用し、個別ウィンドウの位置固定ではありません。
ロック中もサイズ変更・折り畳みはできます。設定の切り替えだけでは設定ファイルへ保存しません。
配置はMaya標準のユーザー設定 ``prefs/workspaces`` へ保存され、シーン保存とは別です。
``saveAs`` は同名配置があれば拒否し、意図した上書きだけ ``overwrite=True`` で許可します。
参照した配置が現在使用中でなければ ``save`` / ``saveAs`` / ``reset`` は拒否します。

``activate`` はMayaの自動保存設定に従い、切り替え元の配置が自動保存される場合があります。
このAPIは自動保存設定を暗黙に変更しません。保存・配置切り替えはシーンUndoによる復元を保証しません。
カスタムUIの再生成には、そのUIのuiScriptや必要プラグインが利用できる必要があります。

通常ウィンドウ
------------------------------------

.. code-block:: python

   from hlib.ui import MainWindow, Window

   window = hlib.getWindow(MainWindow.name())
   print(window.get_size())             # (width, height)
   print(window.getPosition())         # (x, y)、Mayaのtop/left順を変換
   window.set_resizable(False)          # サイズ変更のみ禁止
   window.set_resizable(True)
   print([item.name() for item in Window.list()])

``setPosition(x, y)``、``set_size(width, height)``、``show()``、``hide()`` も使用できます。
``hide`` は削除ではありません。メインウィンドウを非表示にする必要は通常ありません。
UIの所有者はMayaであり、このAPIはメインウィンドウの削除メソッドを提供しません。

ドッキングUI
------------------------------------

.. code-block:: python

   from hlib.ui import WorkspaceControl

   controls = WorkspaceControl.list()
   # 実在する名前を選んで取得する
   if controls:
       control = hlib.getWorkspaceControl(controls[0].name())
       print(control.get_floating(), control.get_size())
       control.show()
       # WorkspaceLayout.unlock()後に明示的に配置を変更する
       # control.dock("right")
       # control.dock("left", target=another_control)
       # control.tab_to(another_control)
       # control.undock()
       # control.set_size(500, 350)  # 浮動状態でのみ使用可能

``set_collapsed`` はタブの親を折り畳むため、同じグループの他タブにも影響します。
``dock`` / ``undock`` / ``tab_to`` は全体ロック中に例外を返します。
``show`` は非表示・最小化・折り畳みを解除し、タブをアクティブにします。

メモリへの一時退避
------------------------------------

.. code-block:: python

   layout = hlib.getWorkspaceLayout()
   snapshot = layout.capture_docking_layout()
   # 同じ配置の中でドッキングを編集する
   layout.restore_docking_layout(snapshot)

   with layout.temporary_docking_layout():
       layout.unlock()
       # 一時的なドッキング変更
       ...
   # 例外時も開始時点の配置とロックへ復元する

``Window`` / ``WorkspaceControl`` にも ``capture`` / ``restore`` / ``temporary_state`` があります。
退避値は変更不可の ``UiSnapshot`` です。``scope`` に保存範囲、``name`` に対象名、
``data`` に取得時点の値を保持し、復元前に元のUIの生存を検証します。
同一セッション内でのみ使用でき、JSON化・ファイル保存・UI再生成には対応しません。

.. list-table:: 退避する範囲
   :header-rows: 1

   * - クラス
     - 対象
     - 対象外
   * - Window
     - Mayaのwindow状態文字列・表示・サイズ変更許可
     - ウィンドウ内部の入力値やツールの実行状態
   * - WorkspaceControl
     - MayaのstateString・表示・折り畳み
     - 周辺タブの配置全体、任意のエディタ内部データ
   * - WorkspaceLayout
     - メインウィンドウのドッキング配置・全体ロック
     - 独立した浮動ウィンドウの位置、エディタ内部データ

全体配置のメモリ復元は、同じ名前の配置が使用中で、退避時にドッキングされていたworkspaceControlが
残っている場合に限ります。ブロック内でUIを削除したり別の配置へ切り替えたりしないでください。
参照はMaya標準のUI削除通知（MUiMessage）で寿命を追跡し、
削除・同名での再作成後の復元は拒否します。監視は最後の参照の解放時に解除します。
hlibはQt関連ライブラリをimportしません。MainWindowはname()でMayaのUI名だけを返し、
Qtの親ウィジェットへの変換は利用側のUI実装で行います。
退避時から浮動していたウィンドウはドッキング退避の検証対象にも含めません。追加されたUIは削除しません。
消えたUIを勝手に再生成せず、復元できない場合は例外を返します。
復元処理自体が失敗した場合、ブロック内の例外は例外チェーンで確認できます。

Maya標準API
------------------------------------

* `window <https://help.autodesk.com/cloudhelp/2026/ENU/Maya-Tech-Docs/CommandsPython/window.html>`_
* `workspaceControl <https://help.autodesk.com/cloudhelp/2026/ENU/Maya-Tech-Docs/CommandsPython/workspaceControl.html>`_
* `workspaceLayoutManager <https://help.autodesk.com/cloudhelp/2026/ENU/Maya-Tech-Docs/CommandsPython/workspaceLayoutManager.html>`_
