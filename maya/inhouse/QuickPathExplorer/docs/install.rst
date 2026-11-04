導入と起動
==========

Windowsで使う
-------------

QPEフォルダー直下の ``QuickPathExplorer.exe`` を起動します。
リポジトリにはビルド済みexeも含まれます。利用するだけなら再ビルドは不要です。

.. code-block:: powershell

   .\QuickPathExplorer.exe 'D:/Projects'

引数のフォルダーを開きます。引数なしでは保存済みの表示を復元します。
Windows 11の通常ウィンドウはOSの角丸を使用し、最大化・スナップ時の形はOSに従います。
Windows標準エクスプローラーと併用できます。

Mayaで使う
----------

#. 使用するMaya年版と一致する ``release/plug-ins/windows/<年>/quickPathExplorer.mll`` を用意します。
#. プラグイン マネージャでロードします。初回のセキュリティ確認は内容を確認して判断してください。
#. **ウィンドウ（Window）→ QuickPathExplorer** を開きます。

MELからも表示できます。

.. code-block:: text

   quickPathExplorer;

Maya起動時にロードする
----------------------

このワークスペースでは ``maya/modules/QuickPathExplorer.mod`` が年別のプラグイン検索先と
起動用 ``scripts`` を登録します。単独配置ではQPEフォルダーを
``MAYA_MODULE_PATH`` に追加し、同梱の ``QuickPathExplorer.mod`` を読み込ませます。

``scripts/userSetup.py`` はGUI起動後に未ロードのプラグインをロードします。
画面とメニューの生成はmllが担当し、バッチ起動では自動ロードしません。
プラグイン マネージャの自動ロードと重なっても二重にロードしません。
QPEはMayaの信頼設定を変更しません。

表示状態と更新
--------------

Mayaでは閉じたときの配置、ドック／フロート、表示状態を保存します。
前回開いていた場合は起動時に復元し、明示的に閉じた場合は閉じた状態を維持します。
設定とプラグインは別に管理します。

更新する前にWindows版を終了してください。Maya版はファイル処理の完了後にアンロードするか、Mayaを終了します。
処理が残る間はアンロードを拒否します。
更新済みmllへPythonの ``reload()`` だけで切り替えることはできません。

配布する場合の同梱資料は :doc:`development` を参照してください。
