hedit ドキュメント
==================

hedit は、Maya 用の Python / MEL スクリプトエディターです。VS Code の Dark+ を参考にした配色、
タブ、行番号、補完候補、出力欄、フォルダーツリー(Explorer)を備えています。
エディター本体は C++ / Qt のプラグインで、Maya と同じプロセスの中で動きます。

.. list-table::
   :widths: 30 70

   * - 対応 Maya
     - 2022(Python 3)・2024・2025・2026・2027(Windows)
   * - 実行方法
     - Maya 標準のスクリプトエディターと同じ経路で実行し、変数も共有します
   * - 追加ライブラリ
     - 不要(Jedi・Pyright・外部辞書などは使いません)
   * - 現在の版
     - |release|

.. toctree::
   :maxdepth: 2
   :caption: はじめに

   overview
   install
   usage

.. toctree::
   :maxdepth: 2
   :caption: リファレンス

   preferences
   shortcuts
   completion
   output
   session

.. toctree::
   :maxdepth: 2
   :caption: 開発・その他

   limitations
   development
   changelog

読む順番の目安
--------------

* はじめて使う: :doc:`overview` → :doc:`install` → :doc:`usage`
* 設定を変えたい: :doc:`preferences`\ (各項目の意味・初期値・使いどころ・注意点を項目ごとに説明しています)
* キー操作を調べたい: :doc:`shortcuts`
* 補完・静的解析・スペルチェックの仕組みを知りたい: :doc:`completion`
* ソースを触る・ビルドする・別リポジトリへ切り出す: :doc:`development`
