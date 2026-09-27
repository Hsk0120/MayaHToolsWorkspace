単位・プラグイン・ワークスペース
============================================================

Mayaの単位設定・プラグインのロード状態・プロジェクト情報を扱います。

例は Maya の Script Editor で実行します。既存ノード名は使用するシーンに合わせてください。
最初に ``import hlib`` を実行してください。

UI単位と内部単位への一時切り替え
----------------------------------

.. code-block:: python

   from hlib.units import Units, native_units

   print(Units.linear(), Units.angle(), Units.time())  # 例: "cm" "deg" "film"
   Units.set_linear("m")

   with native_units():
       # このブロック内は距離=cm、角度=radianとして扱える
       ...
   # ブロックを抜けると開始時点のUI単位(distanceは"m"のまま)へ復元される

``Units`` の取得・設定はいずれも ``cmds.currentUnit`` の文字列表現
(``"cm"``/``"m"``、``"deg"``/``"rad"``、``"film"``/``"ntsc"`` 等)を使います。
設定は Maya の Undo に対応します。``native_units()`` は行列・ベクトル計算など
シーンの表示単位に依存しない処理をしたい場合に使うコンテキストマネージャで、
``om2.MDistance``/``om2.MAngle`` の ``setUIUnit`` を直接呼ぶため MEL の往復が
無く、ブロックを抜ける際(例外時を含む)に開始時点の単位へ復元します
(時間単位には影響しません)。

プラグインのロード状態
------------------------

.. code-block:: python

   from hlib.plugins import Plugin, Plugins

   plugin = Plugin("matrixNodes")
   print(plugin.is_loaded(), plugin.path(), plugin.version())
   plugin.unload()
   plugin.ensure_loaded()   # 未ロードなら冪等にロードする

   for loaded in Plugins.loaded():
       print(loaded.name())

``is_loaded``/``is_registered`` は未知のプラグイン名でも例外にならず ``False``
を返します。``path``/``version`` も未登録なら ``None`` です。
版は ``version_tuple()``(``"3.0.0.0-202602040323-9df3db7"`` のようにビルド情報が付いても
先頭の数字だけを使い、``(3, 0, 0, 0)`` を返す)と ``is_version_at_least("3.0.0")`` で
比較できます。

モジュールと、製品の導入確認
------------------------------

Autodesk 製品(Bifrost・MayaUSD・Arnold など)や ``maya/modules/*.mod`` は、プラグインとは
別に「モジュール」として登録されます。``Module`` はその版と場所を、``PluginPackage`` は
「モジュール + 複数のプラグイン」からなる製品の導入確認・ロード・未導入時の警告を扱います。

.. code-block:: python

   from hlib.plugins import Module, PluginPackage

   print(Module("Bifrost").version())            # "3.0.0.0"(未登録なら None)
   print(Module("Bifrost").is_version_at_least("3.0.0"))

   bifrost = PluginPackage(
       "Bifrost", plugins=("mayaVnnPlugin", "bifrostGraph", "flowWedging"),
       module="Bifrost", version_plugin="bifrostGraph",
       minimum_version="3.0.0", minimum_maya=2025)
   status = bifrost.ensure_loaded()   # "loaded" / "missing" / "outdated" / "load-failed" / "skipped"

``ensure_loaded()`` は、必要な版が導入されていれば全プラグインをロードします。導入されていない・
版が古い場合はプラグインをロードせず、``cmds.warning`` と警告ダイアログ(バッチ・スタンドアロン
では表示しない)で導入が必要なことを知らせます。``minimum_maya`` 未満の Maya では何もしません
(``"skipped"``)。``dialog=False`` で表示を止め、関数を渡すと警告文を受け取れます。
1 回の呼び出しにした ``hlib.requirePlugins(...)`` もあります。

.. code-block:: python

   import hlib

   hlib.requirePlugins(("mayaVnnPlugin", "bifrostGraph", "flowWedging"),
                       minimum_version="3.0.0", module="Bifrost",
                       version_plugin="bifrostGraph", minimum_maya=2025)

``minimum_version`` を指定しない製品は、版を問わずロードを試み、全プラグインをロードできなかった
場合に未導入(``"missing"``)として扱います。

ワークスペース(プロジェクト)
--------------------------------

.. code-block:: python

   from hlib.workspace import Workspace

   print(Workspace.root())               # 現在のワークスペースのルート
   print(Workspace.rule("scene"))        # 例: "scenes"
   print(Workspace.path_for("scene", "myScene.ma"))  # root/scenes/myScene.ma

``Workspace`` はインスタンスを持たず、常に現在のワークスペース(Mayaのセッションに
1つだけ存在するグローバルな状態)を対象にします。``expand`` はファイルルール名を
解決せず、文字通りルートへ相対パスを連結するだけの点に注意してください
(ルールが指すディレクトリを取得する場合は ``path_for`` を使います)。
