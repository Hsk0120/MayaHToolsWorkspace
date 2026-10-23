単位とプラグイン
================

Mayaの単位設定はmaya.cmds.currentUnit、値の変換はmlib.common.unitsを使います。

.. code-block:: python

   import maya.cmds as cmds
   from mlib.common import units
   from mlib.decorator import nativeUnits

   cmds.currentUnit(linear="m")
   with nativeUnits():
       # 一時的に距離cm・角度radを使い、終了時に元へ戻す。
       pass

時間単位はnativeUnitsで変更しません。型・値の境界は :doc:`cmds_interop` を参照してください。

プラグインのロード状態
------------------------

.. code-block:: python

   from mlib.common import Plugin

   plugin = Plugin("matrixNodes")
   print(plugin.isLoaded(), plugin.getPath(), plugin.getVersion())
   plugin.unload()
   plugin.ensureLoaded()   # 未ロードなら冪等にロードする

   for loaded in Plugin.loaded():
       print(loaded.name)

``isLoaded``/``isRegistered`` は未知のプラグイン名でも例外にならず ``False``
を返します。``getPath()``/``getVersion()`` も未登録なら ``None`` です。
``load()`` は呼出し後のロード状態も確認します。Mayaが初期化失敗をPython例外にせず
戻った場合も、未ロードなら ``RuntimeError`` になります。``PluginPackage.tryLoad()`` は
この失敗を ``"load-failed"`` として報告します。
``getVersion()`` は ``Version`` オブジェクトを返します。数値として解釈できない版も ``None``
になります。Mayaが返す文字列が必要なら ``getVersionText()``、数値のタプルが必要なら
``getVersion()`` がNoneでないことを確認して ``version.parts`` を使います。``isVersionAtLeast("3.0.0")`` でも比較できます。

モジュールと、製品の導入確認
------------------------------

Autodesk 製品(Bifrost・MayaUSD・Arnold など)や ``maya/modules/*.mod`` は、プラグインとは
別に「モジュール」として登録されます。``Module`` はその版と場所を、``PluginPackage`` は
「モジュール + 複数のプラグイン」からなる製品の導入確認・ロード・未導入時の警告を扱います。

.. code-block:: python

   from mlib.common import Module, PluginPackage

   print(Module("Bifrost").getVersion())            # Versionの文字列表現(未登録なら None)
   print(Module("Bifrost").isVersionAtLeast("3.0.0"))

   bifrost = PluginPackage(
       "Bifrost", plugins=("mayaVnnPlugin", "bifrostGraph", "flowWedging"),
       module="Bifrost", version_plugin="bifrostGraph",
       minimum_version="3.0.0", minimum_maya=2025)
   status = bifrost.tryLoad()   # "loaded" / "missing" / "outdated" / "load-failed" / "skipped"

   from mlib.common import LOADED
   if status == LOADED:
       print("必要なプラグインをロードできました")

``tryLoad`` の戻り値は状態文字列です。
``"missing"`` などもPythonの真偽評価ではTrueになるため、``if status:`` では
成功判定できません。``status == LOADED`` で確認してください。

``tryLoad()`` は、必要な版が導入されていれば全プラグインをロードします。導入されていない・
版が古い場合はプラグインをロードせず、``mlib.logger.warning`` と警告ダイアログ(バッチ・スタンドアロン
では表示しない)で導入が必要なことを知らせます。``minimum_maya`` 未満の Maya では何もしません
(``"skipped"``)。``dialog=False`` で表示を止め、関数を渡すと警告文を受け取れます。
``minimum_version`` を指定しない製品は、版を問わずロードを試み、全プラグインをロードできなかった
場合に未導入(``"missing"``)として扱います。

実装の配置と版番号ユーティリティ
------------------------------------------------------------

``mlib.common`` は原則1クラス1ファイルで構成します。単数クラスと対応する複数クラスは同じファイルにまとめられます。
``plugin.py`` は ``Plugin``、
``module.py`` は ``Module``、``pluginPackage.py`` は ``PluginPackage`` を定義します。
利用側は引き続き ``from mlib.common import Plugin, Module, PluginPackage``
で取得できます。

ノード型に対応する標準プラグインのロードは ``Plugin.ensureNodePlugin(node_type)``
にまとめています。現在はHumanIKの対象ノードのみ対応し、それ以外の型では何もしません。
``mlib.createNode`` はノード生成時にこのメソッドを使用します。

版番号の値・解析・比較・変更コピーを ``mlib.common.version.Version`` にまとめています。
Mayaに依存しない不変の値クラスで、``mlib.common`` からも取得できます。

.. code-block:: python

   from mlib.common import Version
   from mlib.common import Plugin

   version = Plugin("bifrostGraph").getVersion()
   if version is not None:
       print(version.major, version.minor, version.patch, version.build)
       print(version.parts, version.suffix)
       print(version.isAtLeast("3.0.0"))
       print(version >= Version("3.0.0"))
       changed = version.replace(minor=1)  # 新しい値。プラグイン自体は更新しない
       print(str(changed))

``Version("3.0.0.0-build")`` は4桁と接尾辞を保持します。未指定の ``minor`` / ``patch`` /
``build`` は0として参照します。``parts`` は指定された桁数を維持します。
``replace()`` は未指定の桁と接尾辞を維持し、元の値を変更しません。

比較とハッシュでは末尾のゼロと接尾辞を無視します。
``Version("3.0") == Version("3.0.0-build")`` はTrueです。
SemVerのプレリリース順序(例えばrc版が正式版より小さいという扱い)は実装しません。
演算子ではVersion同士を比較し、文字列との比較には ``isAtLeast()`` を使います。

コンストラクターは不正な入力に例外を出します。取得値の検査には
``Version.parse(value)`` を使うと、空値・不正値がNoneになります。
``PluginPackage.minimumVersion`` / ``getInstalledVersion()`` / ``getLoadedVersion()``
も ``Version | None`` を返します。取得済みの値はスナップショットで、現在の版を得るには
再びプラグインやモジュールへ問い合わせます。

旧 ``parse_version`` / ``isAtLeast`` / ``format_version`` 関数は廃止しました。
``Version.parse(value)`` / ``version.isAtLeast(minimum)`` / ``str(version)`` に移行してください。
従来の ``getVersion()`` の生文字列が必要なコードは ``getVersionText()`` に変更してください。
