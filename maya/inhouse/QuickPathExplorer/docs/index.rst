QuickPathExplorer
=================

深いフォルダーをカラムでたどり、WindowsとMayaで同じ操作を使うファイルブラウザーです。
上段でフォルダーを選び、下段でファイルを操作します。左右のサイドバーは必要なときに開けます。

.. figure:: _static/qpe-columns.gif
   :alt: カラムからRobotのRigを開き、途中の列でHeroやShotsへ切り替える操作
   :target: _static/qpe-columns.gif

   フォルダーを掘る → 途中の列から別の枝へ → ショット作業へ。
   Windows版UIと撮影用サンプルを使った短いループGIFです。クリックすると原寸で開きます。

戻るボタンを何度も押さず、祖先のフォルダーを見渡したまま移動できます。
ワイドな全体画面と手順は :doc:`browsing` を参照してください。

.. list-table::
   :widths: 25 75

   * - Windows版
     - Windows x64向けの ``QuickPathExplorer.exe``。Maya・Pythonの導入は不要です。
   * - Maya版
     - Maya 2022〜2027（Windows）の年別 ``quickPathExplorer.mll``。2022はPython 3で使用します。
   * - 現在の版
     - |release|
   * - 主な機能
     - カラム・タブ・検索、ファイル整理と履歴、MayaのOpen／Save／Import／Reference／FBX

最初に読むページ
----------------

* Windowsで使う、Mayaへ導入する: :doc:`install`
* フォルダーをたどる、タブと一覧を使う: :doc:`browsing`
* ファイルを整理する、検索する: :doc:`files`
* 名前空間やFBXの設定を変える: :doc:`maya`
* 文字サイズ・配色・キーを変える: :doc:`preferences`

.. toctree::
   :maxdepth: 1
   :caption: 使い方

   install
   browsing
   files
   maya
   preferences
   shortcuts

.. toctree::
   :maxdepth: 1
   :caption: 開発・困ったとき

   development
   troubleshooting

このガイドは実装済みのC++／Qt版を説明します。
Windows標準エクスプローラーの置き換え登録や、Mayaファイルの次番号保存は行いません。
