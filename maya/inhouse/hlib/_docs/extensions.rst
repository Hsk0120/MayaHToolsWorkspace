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

``nodes`` と ``plugs`` は任意です。各 ``__init__.py`` に通常のimportと ``__all__`` で
公開クラスを明示し、``_WRAPPER_CLASSES`` 辞書に型名とクラスの対応を宣言します。
``from hlib._core import extensions`` で取得でき、ルートへの再公開は行いません。
それぞれ ``hlib.nodes.Node``、``hlib.plugs.Plug`` を継承してください。
クラスは拡張側の ``nodes`` / ``plugs`` から公開され、hlib直下へは展開しません。
ラッパーモジュールの自動走査やクラスの実行時注入は行いません。

例えば ``nodes/customNode.py`` に定義した ``CustomNode`` は、
``nodes/__init__.py`` で次のように宣言します。型名は実際のMaya nodeTypeに合わせます。

.. code-block:: python

   from .customNode import CustomNode

   __all__ = ["CustomNode"]
   _WRAPPER_CLASSES = {"exampleNode": CustomNode}

``plugs`` も同じ構成で、辞書のキーにはアトリビュート型名を使います。
型対応と公開するクラス名は別の宣言です。登録済み型からのラッパー選択は
hlibの既存規則に従います。

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
``is_available()`` もロード・登録・UI/シーン変更を行わない照会として実装します。
Python依存の遅延importは可能ですが、その依存のimport時にもMayaを編集しないでください。

依存の方向は「拡張 → hlib公開API」に限定します。拡張同士のimport・継承は
行わず、組合せ処理はhrigなど利用側のツールへ置きます。宣言と利用可否を確認し、
利用可能な拡張について登録前にPythonソースの
import文とラッパーの基底クラスを検査し、他の拡張への依存を拒否します。
動的importはソース検査で検出できないため、作者側でも同じ規則を守ってください。
``__init__.py`` からhlibをimportすると初期化途中で検出されるため、エラーになります。
サブパッケージを公開する場合は、宣言完了後の明示importまたは遅延importを使います。

状態とリロード
--------------

コア名を変更した場合は、拡張も同じ接頭辞へ変更します。
例えば ``mlib`` は ``mlib_*`` だけを検出します。拡張内でコアを参照する方法と
固定の宣言識別子については :doc:`package_names` を参照してください。

.. code-block:: python

   import hlib
   from hlib._core import extensions

   print(extensions.status())
   print(extensions.diagnostics())
   hlib.reload()

状態は ``loaded``（登録済み）、``unavailable``（依存未導入）、
``skipped``（宣言が未対応）、``error``（読み込み・検証失敗）です。
失敗理由は ``reason`` に入り、エラーはログにも出力します。
外部依存がなくてもhlib標準機能は利用できます。
``status()`` は最後の初期化結果のコピーです。後から依存プラグインを明示ロードしても
自動では更新されません。現在の可用性は ``diagnostics()`` で分けて照会します。

.. code-block:: python

   result = extensions.diagnostics()  # getDiagnostics()の省略入口。
   bifrost = result.get("hlib_bifrost")
   if bifrost is not None:
       print(bifrost["initialization"])  # statusと同じ初期化結果、未初期化ならNone。
       print(bifrost["available"])       # 現在の依存可用性。True/False/None。
       print(bifrost["reason"])

診断は既にimport済みの宣言の ``is_available`` だけを呼びます。
新しい拡張のimport、型登録、プラグインロード、reloadは行いません。
未import・初期化中・照会の再入・例外・非boolの戻り値ではavailableがNoneとなり、
reasonに理由を返します。Falseは依存が現在利用不可と照会できた場合です。
初期化状態と型登録は更新されないため、状態表示だけの目的でreloadする必要はありません。

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
専用クラスは ``hlib.node()`` / ``hlib.ls()`` から自動で選ばれます。
``setRadius()`` はUndo可能です。``native_api()`` から外部APIを直接操作する場合は
そのAPI自身のUndoと副作用の仕様に従います。
