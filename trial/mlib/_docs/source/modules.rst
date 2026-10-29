モジュールリファレンスマニュアル
================================

各モジュールにクラス・関数・引数・戻り値を掲載しています。

Main
----

公開パッケージと、対象の取得・作成・検索・削除・複製・選択のコマンド入口です。

.. toctree::
   :maxdepth: 1

   autoapi/mlib/index
   autoapi/mlib/cmds/index

Nodes and Attributes
--------------------

ノードの階層・変換・専門編集と、アトリビュートの値・接続・マルチアトリビュートを扱います。

.. toctree::
   :maxdepth: 1

   autoapi/mlib/nodes/index
   autoapi/mlib/plugs/index

Components
----------

頂点・エッジ・フェース・UV・CVと、それらのコレクションを参照します。

.. toctree::
   :maxdepth: 1

   autoapi/mlib/components/index

Data Types
----------

Vector・Matrix・Quaternionなど、OpenMayaを基盤とした可変の数学値です。

.. toctree::
   :maxdepth: 1

   autoapi/mlib/maths/index

Common Features
---------------

選択・単位・プラグイン・イベント等の共通機能、Undo等のコンテキスト、ログ、汎用関数です。

.. toctree::
   :maxdepth: 1

   autoapi/mlib/common/index
   autoapi/mlib/decorator/index
   autoapi/mlib/logger/index
   autoapi/mlib/util/index

Development
-----------

型登録・参照解決・再読み込み・拡張管理などの基盤です。
内部補助も掲載されるため、利用する入口は各モジュールの説明と公開名を確認してください。

.. toctree::
   :maxdepth: 1

   autoapi/mlib/core/index

Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
