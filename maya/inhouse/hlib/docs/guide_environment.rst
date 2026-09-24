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
