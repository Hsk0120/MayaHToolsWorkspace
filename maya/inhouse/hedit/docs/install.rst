導入と起動
==========

ワークスペースの起動バッチで使う場合
------------------------------------

このリポジトリの ``maya/maya_<バージョン>_en.bat`` から Maya を起動すると、
``maya/modules/hedit.mod`` が自動で読み込まれます。

``hedit.mod`` は、Maya のバージョン別のプラグインパス
(``hedit/release/plug-ins/windows/<Mayaの年>/<hedit の版>/``)と、
起動時に ``hedit.mll`` を自動ロードするための最小の Python(``scripts/userSetup.py``)を設定します。

hedit のロジック(復元・Window メニュー登録・補完・静的解析・タブ保存など)自体は
``.py`` ファイルを持たず、``hedit.mll`` 自身に同梱されています(:doc:`development` 参照)。
プラグインのロード時に、Maya 同梱の Python から ``import hedit`` できるようになります。
Plug-in Manager からの明示ロードでも、この ``userSetup.py`` 経由の自動ロードでも、
起こることは同じです。``userSetup.py`` が行うのは ``cmds.loadPlugin('hedit')`` の
呼び出しだけで、復元やメニュー登録のロジックはここには置いていません。

Maya の GUI が起動すると、\ ``userSetup.py`` が次の idle で ``hedit`` プラグインを
ロードします。これを契機に ``initializePlugin``\ (C++)が Window メニューへの項目追加と、
前回開いていた場合の画面復元まで自動的に行います。

.. note::

   * 初回は編集画面を開きません。前回 hedit を開いたまま Maya を終了した場合だけ、画面とタブを復元します。
   * バッチモードと standalone(mayapy)では自動ロードしません(``initializePlugin`` 自体は動きます)。
   * Maya の Security 設定で ``userSetup`` の実行を禁止している場合は迂回しません。その場合は
     Plug-in Manager で ``hedit`` を明示ロードするか、Plug-in Manager の ``hedit`` 行で
     「Auto load」にチェックしてください(Maya 標準の永続設定で、hedit 自身は変更しません)。
   * ``.mod`` を追加・変更した後は、起動済みの Maya を再起動してください。

画面を開く
----------

``hedit`` をロードすると(起動時の自動ロード・Plug-in Manager のどちらでも)、
Window メニューの末尾に区切り線と **hedit - Python / MEL**\ (緑の H アイコン)が追加されます。
これをクリックして開くのが基本の起動方法です。プラグインをアンロードすると、この項目も取り除かれます。

メニュー項目のコマンドは次と同じなので、Python タブからも開けます。

.. code-block:: python

   import hedit
   hedit.show()

``import hedit`` は、\ ``hedit`` プラグインをロードした後で使えます。プラグインが未ロードのまま
``import hedit`` を実行すると ``ModuleNotFoundError`` になるため、先にロードしてください。
mayapy(standalone)から補完などの Python API を使う場合も同様です。

.. code-block:: python

   from maya import cmds
   cmds.loadPlugin('hedit')   # .mod の MAYA_PLUG_IN_PATH から名前で見つかる
   import hedit

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

* C++ プラグイン(``.mll``)は Python の ``reload()`` では更新されません。hedit の Python 部分も ``.mll`` に
  同梱されているため同様です。更新後は Maya を再起動してください。
* ``scripts/hedit/*.py`` を使っていた旧版から更新した場合も、Maya の再起動だけで切り替わります。
  ``scripts/hedit`` に ``__pycache__`` だけが残っていても、同梱の ``hedit`` が優先されるため影響はありません(削除して構いません)。
* フォルダー名・パッケージ名・プラグイン名は小文字の ``hedit`` です。旧名 ``heditor`` の保存先(未保存タブ・UI 状態・設定)は、
  新しい保存先に同名のファイルがまだない場合だけ ``hedit`` へコピーします。旧データは削除しません。

配置していないバージョンでは
----------------------------

対応する ``hedit.mll`` が ``MAYA_PLUG_IN_PATH`` に見つからない Maya では、Plug-in Manager での
ロードや ``cmds.loadPlugin('hedit')`` が Maya 標準のエラー(プラグインが見つからない旨)になります。
その場合は :doc:`development` の手順でビルドしてください。
