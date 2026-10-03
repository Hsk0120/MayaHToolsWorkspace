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
      └─ customPlug.py

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

依存の方向は「拡張 → hlib公開API」に限定します。拡張同士のimport・継承は
行わず、組合せ処理はhrigなど利用側のツールへ置きます。宣言と利用可否を確認し、
利用可能な拡張について登録前にPythonソースの
import文とラッパーの基底クラスを検査し、他の拡張への依存を拒否します。
動的importはソース検査で検出できないため、作者側でも同じ規則を守ってください。
``__init__.py`` からhlibをimportすると初期化途中で検出されるため、エラーになります。
サブパッケージを公開する場合は、宣言完了後の明示importまたは遅延importを使います。

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
``is_available()`` がFalseの拡張は実装のソース解析を行いません。
対象Maya/Pythonで読み込めない実装を含む場合は、この関数で利用不可を返してください。
宣言用の ``__init__.py`` 自体は対象Pythonで読み込める必要があります。

同名パッケージが異なる探索場所にある場合はエラーにします。
型の衝突も上書きせずエラーにし、その拡張の登録全体を見送ります。
異なる拡張間の衝突では名前順で先に登録された拡張が残ります。
アトリビュート型の登録は全ノード共通です。特定ノードのために ``double3`` など
標準のアトリビュート型を上書きする用途には使えません。

``hlib.reload()`` だけで本体と拡張を更新します。宣言済みの拡張と、読み込みに
失敗した拡張の残存モジュールをまとめて
読み込み解除し、本体を依存順に再読み込みしてから、拡張を再検出・登録します。
外部SDKとMayaプラグインは再読み込みしません。拡張初期化中のreloadは拒否します。
保持済みインスタンス・外部でimport済みのクラスやパッケージ参照は取得し直してください。
探索パスから外した拡張の型登録は次のリロードで消えます。

.. code-block:: python

   import hlib
   hlib.reload()

   # 新しい拡張パッケージ参照を取得する。
   import hlib_bifrost
   graphs = hlib.ls(type="bifrostGraphShape")
   if graphs:
       graph = hlib_bifrost.nodes.Graph(graphs[0])

現在のBifrostの ``Graph`` は専用参照クラスです。``ls`` が自動で ``Graph`` を
返す登録ラッパーではないため、グラフ内部を扱う場合は上記のように変換します。

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
       solver.setRadius(45.0)

``UEPoseBlenderNode`` は ``driven_transform()`` と ``envelope()`` を提供します。
専用クラスは ``hlib.getNode()`` / ``hlib.ls()`` から自動で選ばれます。
``setRadius()`` はUndo可能です。``native_api()`` から外部APIを直接操作する場合は
そのAPI自身のUndoと副作用の仕様に従います。
