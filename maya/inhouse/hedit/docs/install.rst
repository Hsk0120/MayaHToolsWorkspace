導入と起動
==========

ワークスペースの起動バッチで使う場合
------------------------------------

このリポジトリの ``maya/maya_<バージョン>_en.bat`` から Maya を起動すると、
``maya/modules/hedit.mod`` が自動で読み込まれます。

``hedit.mod`` は次を設定します。

* Python のパス(``hedit/scripts``)
* Maya のバージョン別のプラグインパス(``hedit/release/plug-ins/windows/<Mayaの年>/<hedit の版>/``)
* 起動時の処理(``scripts/userSetup.py``)

Maya の GUI が起動すると、\ ``userSetup.py`` が ``hedit.startup.initialize()`` を遅延実行して、
プラグインの読み込みと Window メニューへの項目の追加を行います。

.. note::

   * 初回は編集画面を開きません。前回 hedit を開いたまま Maya を終了した場合だけ、画面とタブを復元します。
   * バッチモードと standalone(mayapy)では自動で読み込みません。
   * Maya の Security 設定で ``userSetup`` の実行を禁止している場合は迂回しません。その場合は、Window メニューまたは ``hedit.show()`` から開いてください。
   * ``.mod`` を追加・変更した後は、起動済みの Maya を再起動してください。

画面を開く
----------

Python タブで次を実行します。

.. code-block:: python

   import hedit
   hedit.show()

Window メニュー末尾の項目(緑の H アイコン)からも開けます。
Plug-in Manager で ``hedit`` を明示的にロードした場合も、同じ項目を追加します。

``show()`` の引数:

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - 呼び出し
     - 動作
   * - ``hedit.show()``
     - 既存の配置を保ったまま開く。初回はフローティング表示。
   * - ``hedit.show(floating=False)``
     - コード側から下側へドッキングして開く。
   * - ``hedit.show(floating=True)``
     - フローティング表示に戻す。

繰り返し ``show()`` や Window メニューを実行すると、既存の本文を一度閉じて同じ画面を開き直します。
未保存のタブ・編集状態・ドッキング位置は保持します。プラグインのアンロードやコードの再読み込みではありません。

初回はフローティング表示です。Maya のドックのタイトル部分をドラッグして、好きな位置へ配置してください。

プラグインの信頼確認
--------------------

Maya が「信頼されていない場所からのロード」の確認を出した場合は、Maya の画面で確認してください。
hedit は Security 設定を変更しません。プラグインのフォルダーを信頼済みの場所へ登録するには、
Preferences → Security → Plug-ins の「My trusted plugin locations」に追加します。

更新するとき
------------

* C++ プラグイン(``.mll``)は Python の ``reload()`` では更新されません。編集中のスクリプトを保存して Maya を再起動してください。
* 旧版からの更新では、初回の再起動の前に、編集中のコードをファイルへ保存してください。
* フォルダー名・パッケージ名・プラグイン名は小文字の ``hedit`` です。旧名 ``heditor`` の保存先(未保存タブ・UI 状態・設定)は、
  新しい保存先に同名のファイルがまだない場合だけ ``hedit`` へコピーします。旧データは削除しません。

配置していないバージョンでは
----------------------------

対応する ``hedit.mll`` がない Maya では、\ ``hedit.show()`` が次のような例外を出します。

.. code-block:: text

   RuntimeError: heditをこのMaya用にビルドしてください: <plug-ins/.../hedit.mll のパス>

その場合は :doc:`development` の手順でビルドしてください。
