パッケージ名の変更
====================

コアと拡張を、同じ接頭辞の名前へ変更できます。例えばコアを ``mlib`` にすると、
Bifrost拡張は ``mlib_bifrost``、PoseDriverConnect拡張は ``mlib_posedriverconnect`` です。
内部import、型登録、拡張検出、reload、ロガー名は実際のパッケージ名に追従します。

配置と利用側
------------

Mayaを終了してからコアのPythonパッケージフォルダーと、対応する拡張のフォルダーを
同じ接頭辞へ変更してください。コア名はPythonでimportできるトップレベルの識別子とし、
既存の標準ライブラリやMayaモジュールと衝突しない名前にします。
拡張名は ``<コア名>_<サフィックス>`` で、サフィックスは小文字英字で始まる
小文字英字・数字・アンダースコアです。コア名のアンダースコアも使用できます。

PoseDriverConnectは ``scripts`` 内にPythonパッケージがあるため、外側の導入フォルダーだけでなく
``scripts/hlib_posedriverconnect`` に相当するフォルダー名も変更してください。
``PYTHONPATH`` には各Pythonパッケージの親フォルダーを追加します。
Mayaの ``.mod`` や起動バッチに固定パスがある場合は、利用環境側で更新してください。

.. code-block:: python

   import mlib
   import mlib_bifrost

   node = mlib.createNode("transform")
   node.plug("translateX").set(10)
   print(mlib.extensions.status())
   mlib.reload()

利用側に書かれた ``import hlib`` や完全修飾名の文字列は自動変更しません。
hrig・HToolsや独自ツールも、採用した名前へ更新してから使用してください。
旧名への互換エイリアスは作りません。起動中のフォルダー名変更は行わず、Mayaを再起動します。
reload後は保持していたクラスやインスタンスを取得し直してください。
異なるコア名のオブジェクトを混在させる相互変換は提供しません。

拡張作者向け
------------

拡張内部は相対importを使い、コアは自身の拡張名から既知のサフィックスを取り除いて求めます。
以下は ``<コア名>_example`` のルートに置く補助モジュールの例です。
コア名にもアンダースコアを使えるため、最初のアンダースコアで分割しないでください。

.. code-block:: python

   from importlib import import_module

   def coreModule(suffix=""):
       name = __package__[:-len("_example")]
       return import_module(name + ("." + suffix if suffix else ""))

この関数はラッパーや依存確認の処理から使います。拡張のルート ``__init__.py`` では
コアをimportせず、宣言だけを完了します。詳細は :doc:`extensions` を参照してください。
同じ接頭辞の拡張だけが検出・再読み込み対象になります。
拡張同士の依存禁止、重複型の拒否、依存未導入時の扱いは名前変更後も同じです。

``HLIB_EXTENSION_API``、``__hlib_node_type__`` などの登録規約、
JSONの ``format="hlib.json"`` は固定の識別子です。パッケージ名と一緒に変更しません。
これにより同じ保存形式と宣言を別名環境でも使えます。

Sphinx
------

``docs/conf.py`` は親フォルダー名から対象名を取得します。
変更後のパッケージ内の ``docs`` を通常どおりビルドすると、タイトル・本文のimport例・
API参照・コマンドページ・クラス継承図のリンクが追従します。
本文の変換はビルド時だけ行い、ソースファイルを一括置換する必要はありません。
JSON形式識別子や宣言定数は変更しません。ビルドにMayaのimportは不要です。

名前を変更した環境では、以前のHTML出力と混在しない新しい出力先へビルドしてください。
外部URL、利用側の設定ファイル、保存済みpickleのPythonモジュールパスは変換対象外です。
