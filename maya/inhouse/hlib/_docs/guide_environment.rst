単位・プラグイン・ワークスペース
============================================================

Mayaの単位設定・プラグインのロード状態・プロジェクト情報を扱います。

例は Maya の Script Editor で実行します。既存ノード名は使用するシーンに合わせてください。
最初に ``import hlib`` を実行してください。

UI単位と内部単位への一時切り替え
----------------------------------

.. code-block:: python

   from hlib.common import Preferences
   from hlib.decorator import nativeUnits

   print(Preferences.linearUnit(), Preferences.angleUnit(), Preferences.timeUnit())  # 例: "cm" "deg" "film"
   Preferences.setLinearUnit("m")

   with nativeUnits():
       # このブロック内は距離=cm、角度=radianとして扱える
       ...
   # ブロックを抜けると開始時点のUI単位(distanceは"m"のまま)へ復元される

``Preferences`` の単位取得・設定は ``cmds.currentUnit`` の文字列表現
(``"cm"``/``"m"``、``"deg"``/``"rad"``、``"film"``/``"ntsc"`` 等)を使います。
設定は Maya の Undo に対応します。``nativeUnits()`` は行列・ベクトル計算など
シーンの表示単位に依存しない処理をしたい場合に使うコンテキストマネージャで、
``om2.MDistance``/``om2.MAngle`` の ``setUIUnit`` を直接呼ぶため MEL の往復が
無く、ブロックを抜ける際(例外時を含む)に開始時点の単位へ復元します
(時間単位には影響しません)。

Preferencesの設定操作
------------------------------------------------------------

.. code-block:: python

   Preferences.upAxis()  # "y" / "z"
   Preferences.setUpAxis("y")
   Preferences.setTrackSelectionOrder(True)

   Preferences.autosaveEnabled()
   Preferences.setAutosaveInterval(600)  # 秒。保存は実行しない
   Preferences.setAutosaveDirectory("D:/maya_autosave")
   Preferences.autosaveDirectory()  # 実際の保存先をPathで取得

   Preferences.undoEnabled()
   Preferences.setUndoLimit(100)  # 無限を無効にし、上限100へ
   Preferences.setUndoInfinite(True)

保存区分と永続化の注意点は :doc:`settings_storage` を参照してください。

Preferencesは現在のMaya設定を扱います。距離・角度・時間単位は現在のシーンに作用し、
新規シーンの既定単位は変更しません。set_time_unitはMaya標準の挙動に従い、
キーの実時間を維持してフレーム番号を調整します。
set_up_axisは既定ではカメラを回転せず、rotate_view=Trueで表示の回転も指定できます。
自動保存先の指定は指定フォルダー方式へ切り替えます。フォルダー作成・保存実行は行いません。

setUndoEnabled(enabled, flush=True)はMaya標準のstateフラグで切り替えます。
無効化で履歴が消去されます。flush=Falseは履歴を保持しますが、
無効中にノード削除などを行うと、保持した履歴で正しくUndoできなくなる場合があります。
Undoの有効・無効、無限、上限の変更はUndoチャンクへまとめません。
上限を減らすと古い履歴が削除され得ます。

旧Unitsクラスは廃止しました。単位設定はPreferencesへ、値の変換は
``from hlib.common import units`` のconvert_distance/distance_to_ui等へ移しました。
一時的な単位切り替えは ``hlib.decorator`` を使用します。

プラグインのロード状態
------------------------

.. code-block:: python

   from hlib.common import Plugin

   plugin = Plugin("matrixNodes")
   print(plugin.isLoaded(), plugin.path(), plugin.version())
   plugin.unload()
   plugin.ensureLoaded()   # 未ロードなら冪等にロードする

   for loaded in Plugin.loaded():
       print(loaded.name())

``isLoaded``/``registered`` は未知のプラグイン名でも例外にならず ``False``
を返します。``path``/``version`` も未登録なら ``None`` です。
``load()`` は呼出し後のロード状態も確認します。Mayaが初期化失敗をPython例外にせず
戻った場合も、未ロードなら ``RuntimeError`` になります。``PluginPackage.tryLoad()`` は
この失敗を ``"load-failed"`` として報告します。
``version()`` は ``Version`` オブジェクトを返します。数値として解釈できない版も ``None``
になります。Mayaが返す文字列が必要なら ``versionText()``、数値のタプルが必要なら
``version()`` がNoneでないことを確認して ``version.parts`` を使います。``versionAtLeast("3.0.0")`` でも比較できます。

モジュールと、製品の導入確認
------------------------------

Autodesk 製品(Bifrost・MayaUSD・Arnold など)や ``maya/modules/*.mod`` は、プラグインとは
別に「モジュール」として登録されます。``Module`` はその版と場所を、``PluginPackage`` は
「モジュール + 複数のプラグイン」からなる製品の導入確認・ロード・未導入時の警告を扱います。

.. code-block:: python

   from hlib.common import Module, PluginPackage

   print(Module("Bifrost").version())            # Versionの文字列表現(未登録なら None)
   print(Module("Bifrost").versionAtLeast("3.0.0"))

   bifrost = PluginPackage(
       "Bifrost", plugins=("mayaVnnPlugin", "bifrostGraph", "flowWedging"),
       module="Bifrost", version_plugin="bifrostGraph",
       minimumVersion="3.0.0", minimumMaya=2025)
   status = bifrost.tryLoad()   # "loaded" / "missing" / "outdated" / "load-failed" / "skipped"

``tryLoad()`` は、必要な版が導入されていれば全プラグインをロードします。導入されていない・
版が古い場合はプラグインをロードせず、``cmds.warning`` と警告ダイアログ(バッチ・スタンドアロン
では表示しない)で導入が必要なことを知らせます。``minimumMaya`` 未満の Maya では何もしません
(``"skipped"``)。``dialog=False`` で表示を止め、関数を渡すと警告文を受け取れます。
1 回の呼び出しにした ``hlib.requirePlugins(...)`` もあります。

.. code-block:: python

   import hlib

   hlib.requirePlugins(("mayaVnnPlugin", "bifrostGraph", "flowWedging"),
                       minimumVersion="3.0.0", module="Bifrost",
                       version_plugin="bifrostGraph", minimumMaya=2025)

``minimumVersion`` を指定しない製品は、版を問わずロードを試み、全プラグインをロードできなかった
場合に未導入(``"missing"``)として扱います。

実装の配置と版番号ユーティリティ
------------------------------------------------------------

``hlib.common`` は原則1クラス1ファイルで構成します。単数クラスと対応する複数クラスは同じファイルにまとめられます。
``plugin.py`` は ``Plugin``、
``module.py`` は ``Module``、``package.py`` は ``PluginPackage`` を定義します。
利用側は引き続き ``from hlib.common import Plugin, Module, PluginPackage``
で取得できます。

ノード型に対応する標準プラグインのロードは ``Plugin.ensureNodePlugin(node_type)``
にまとめています。現在はHumanIKの対象ノードのみ対応し、それ以外の型では何もしません。
``hlib.createNode`` はノード生成時にこのメソッドを使用します。

版番号の値・解析・比較・変更コピーを ``hlib.common.version.Version`` にまとめています。
Mayaに依存しない不変の値クラスで、``hlib.common`` からも取得できます。

.. code-block:: python

   from hlib.common import Version
   from hlib.common import Plugin

   version = Plugin("bifrostGraph").version()
   if version is not None:
       print(version.major, version.minor, version.patch, version.build)
       print(version.parts, version.suffix)
       print(version.atLeast("3.0.0"))
       print(version >= Version("3.0.0"))
       changed = version.replace(minor=1)  # 新しい値。プラグイン自体は更新しない
       print(str(changed))

``Version("3.0.0.0-build")`` は4桁と接尾辞を保持します。未指定の ``minor`` / ``patch`` /
``build`` は0として参照します。``parts`` は指定された桁数を維持します。
``replace()`` は未指定の桁と接尾辞を維持し、元の値を変更しません。

比較とハッシュでは末尾のゼロと接尾辞を無視します。
``Version("3.0") == Version("3.0.0-build")`` はTrueです。
SemVerのプレリリース順序(例えばrc版が正式版より小さいという扱い)は実装しません。
演算子ではVersion同士を比較し、文字列との比較には ``atLeast()`` を使います。

コンストラクターは不正な入力に例外を出します。取得値の検査には
``Version.parse(value)`` を使うと、空値・不正値がNoneになります。
``PluginPackage.minimumVersion()`` / ``installedVersion()`` / ``loadedVersion()``
も ``Version | None`` を返します。取得済みの値はスナップショットで、現在の版を得るには
再びプラグインやモジュールへ問い合わせます。

旧 ``parse_version`` / ``isAtLeast`` / ``format_version`` 関数は廃止しました。
``Version.parse(value)`` / ``version.atLeast(minimum)`` / ``str(version)`` に移行してください。
従来の ``version()`` の生文字列が必要なコードは ``versionText()`` に変更してください。

ワークスペース(プロジェクト)
--------------------------------

.. code-block:: python

   from hlib.common.workspace import Workspace

   print(Workspace.root())               # 現在のワークスペースのルート
   print(Workspace.rule("scene"))        # 例: "scenes"
   print(Workspace.pathFor("scene", "myScene.ma"))  # root/scenes/myScene.ma

``Workspace`` はインスタンスを持たず、常に現在のワークスペース(Mayaのセッションに
1つだけ存在するグローバルな状態)を対象にします。``expand`` はファイルルール名を
解決せず、文字通りルートへ相対パスを連結するだけの点に注意してください
(ルールが指すディレクトリを取得する場合は ``pathFor`` を使います)。
