任意拡張パッケージ
==================

``import hlib`` の最後に、Python探索パス直下の ``hlib_*`` パッケージを
自動検出します。拡張名をhlib本体へ追加する必要はありません。
``userSetup.py`` や独自Mayaプラグインは不要です。

パッケージの規則
----------------

名前は ``hlib_<拡張名>`` とし、拡張名は英小文字で始まる小文字・数字・
アンダースコアにします。通常の ``__init__.py`` を持つパッケージを対象とし、
Python探索パス直下だけを調べます。

.. code-block:: text

   hlib_example/
   ├─ __init__.py
   ├─ nodes/
   │  ├─ __init__.py
   │  └─ customNode.py
   └─ plugs/
      ├─ __init__.py
      └─ custom_plug.py

``nodes`` と ``plugs`` は任意です。各フォルダー直下のモジュールを検出します。
クラスには ``hlib.extensions.node_wrapper`` または ``plug_wrapper`` を使います。
それぞれ ``hlib.nodes.Node``、``hlib.plugs.Plug`` を継承してください。
クラスは拡張側の ``nodes`` / ``plugs`` から公開され、hlib直下へは展開しません。

``__init__.py`` では拡張APIバージョンと依存確認を定義します。
以下の ``example_sdk`` は説明用の名前です。

.. code-block:: python

   HLIB_EXTENSION_API = 1

   def is_available():
       try:
           import example_sdk
       except ModuleNotFoundError as exc:
           if exc.name != "example_sdk":
               raise
           return False
       return True

このファイルのimport時にUI・シーン編集・外部プラグインのロードは行わず、
専用ラッパーも先にimportしないでください。候補の宣言を確認するため、
``hlib_*`` に一致したパッケージの ``__init__.py`` は実行されます。
信頼するパッケージだけをPython探索パスへ追加してください。

状態とリロード
--------------

.. code-block:: python

   import hlib
   print(hlib.extensions.status())
   hlib.reload()

状態は ``loaded``（登録済み）、``unavailable``（依存未導入）、
``skipped``（宣言が未対応）、``error``（読み込み・検証失敗）です。
失敗理由は ``reason`` に入り、エラーはログにも出力します。
外部依存がなくてもhlib標準機能は利用できます。

同名パッケージが異なる探索場所にある場合はエラーにします。
型の衝突も上書きせずエラーにし、その拡張の登録全体を見送ります。
異なる拡張間の衝突では名前順で先に登録された拡張が残ります。
属性型の登録は全ノード共通です。特定ノードのために ``double3`` など
標準の属性型を上書きする用途には使えません。

``hlib.reload()`` は標準登録を作り直した後、拡張パッケージも新しい
hlib基底クラスを参照するよう読み直します。外部SDK自体は再読み込みしません。
保持済みインスタンス・外部でimport済みのクラス参照は取得し直してください。
探索パスから外した拡張の型登録は次のリロードで消えます。

PoseDriverConnectサンプル
----------------------------------------

``hlib_posedriverconnect`` は ``epic_pose_wrangler`` のv2モデルAPIを使用します。
同梱の ``hlib_posedriverconnect.mod`` で拡張の探索パスを追加できます。
PoseDriverConnect本体のPythonパス・対応Mayaプラグインは別途必要です。
外部APIのPython依存 ``six`` も必要です。導入済み本体の依存不足は
``error`` として報告し、hlib標準機能は継続します。自動インストールはしません。
登録時にプラグインのロードやUI起動は行いません。

.. code-block:: python

   import hlib

   # 対応プラグインと既存ソルバーがある環境で実行
   for solver in hlib.ls(type="UERBFSolverNode"):
       print(solver.drivers())
       print(solver.num_poses())
       print(solver.radius())
       solver.set_radius(45.0)

``UEPoseBlenderNode`` は ``driven_transform()`` と ``envelope()`` を提供します。
専用クラスは ``hlib.node()`` / ``hlib.ls()`` から自動で選ばれます。
``set_radius()`` はUndo可能です。``native_api()`` から外部APIを直接操作する場合は
そのAPI自身のUndoと副作用の仕様に従います。
