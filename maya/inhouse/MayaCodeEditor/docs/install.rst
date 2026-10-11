導入と起動
==========

ワークスペースの起動バッチで使う場合
------------------------------------

このリポジトリの ``maya/maya_<バージョン>_en.bat`` から Maya を起動すると、
``maya/modules/MayaCodeEditor.mod`` が自動で読み込まれます。

``MayaCodeEditor.mod`` は、Maya のバージョン別のプラグインパス
(``Maya Code Editor/release/plug-ins/windows/<Mayaの年>/``\ 。版のフォルダーは作らないので、版を上げても場所は変わりません)と、
起動時に ``mayaCodeEditor.mll`` を自動ロードするための最小の Python(``scripts/userSetup.py``)を設定します。

Maya Code Editor のロジック(Window メニュー登録・ドッキング・開閉状態の保存と復元・タブ保存・補完・静的解析など)は
``.py`` ファイルを持たず、``mayaCodeEditor.mll`` 自身が持っています(:doc:`development` 参照)。
画面・ドック・状態の保存は C++ で、補完と構文チェックだけを Maya 同梱の Python で行います。
Plug-in Manager からの明示ロードでも、この ``userSetup.py`` 経由の自動ロードでも、
起こることは同じです。``userSetup.py`` が行うのは ``cmds.loadPlugin('mayaCodeEditor')`` の
呼び出しだけで、復元やメニュー登録のロジックはここには置いていません。

Maya の GUI が起動すると、\ ``userSetup.py`` が次の idle で ``mayaCodeEditor`` プラグインを
ロードします。これを契機に ``initializePlugin``\ (C++)が Window メニューへの項目追加と、
前回開いていた場合の画面復元まで自動的に行います。

.. note::

   * 初回は編集画面を開きません。前回 Maya Code Editor を開いたまま Maya を終了した場合だけ、画面とタブを復元します。
   * バッチモードと standalone(mayapy)では自動ロードしません(``initializePlugin`` 自体は動きます)。
   * Maya の Security 設定で ``userSetup`` の実行を禁止している場合は迂回しません。その場合は
     Plug-in Manager で ``mayaCodeEditor`` を明示ロードするか、Plug-in Manager の ``mayaCodeEditor`` 行で
     「Auto load」にチェックしてください(Maya 標準の永続設定で、Maya Code Editor 自身は変更しません)。
   * ``.mod`` を追加・変更した後は、起動済みの Maya を再起動してください。
   * Maya Code Editor は、Maya のワークスペースの復元だけでは自分をロードしません(オートロードを切っていれば、
     保存済みの Maya Code Editor のドックがあってもロードされません。その場合ドックは表示せずに隠します)。

mayaCodeEditor.mll 単体で使う場合
---------------------------------

ビルド環境の無い場所(会社の PC など)では、\ ``release/plug-ins/windows/<Mayaの年>/mayaCodeEditor.mll`` だけを
固定のフォルダーに置き、Plug-in Manager の「Browse」でロードするか、そのフォルダーを ``MAYA_PLUG_IN_PATH`` に加えます。

* フォルダーは版で変えないでください。Maya の「信頼できるプラグインの場所」とオートロードは、フォルダーとファイルの場所で
  覚えています。版ごとに場所を変えると、そのたびに「信頼できないプラグインのロード」の確認が出て、確認で拒否したり
  ロードに失敗したりすると、オートロードの設定が外れます。
* 初回のロードで確認が出たら、Preferences → Security → Plug-ins の「My trusted plugin locations」にそのフォルダーを
  追加します(スクリプトからは登録できません)。
* ``mayaCodeEditor.mll`` には版などのファイル情報(エクスプローラーの「プロパティ → 詳細」)が入っています。
  デジタル署名はしていないため、会社のウイルス対策ソフトが警告する場合は、管理者にフォルダー単位の除外を依頼してください。

画面を開く
----------

``mayaCodeEditor`` をロードすると(起動時の自動ロード・Plug-in Manager のどちらでも)、
Window メニューの末尾に区切り線と **Maya Code Editor**\ (緑の H アイコン)が追加されます。
これをクリックして開くのが基本の起動方法です。プラグインをアンロードすると、この項目も取り除かれます。

メニュー項目のコマンドは MEL の ``mayaCodeEditor -show`` です。MEL タブ・シェルフ・ホットキーから同じように開けます。

.. code-block:: text

   mayaCodeEditor -show;

Python からは、同じ動作をする ``maya_code_editor.show()`` を使えます(C++ の ``mayaCodeEditor`` コマンドを呼ぶだけの窓口です)。

.. code-block:: python

   import maya_code_editor
   maya_code_editor.show()

``import maya_code_editor`` は、\ ``mayaCodeEditor`` プラグインをロードした後で使えます。プラグインが未ロードのまま
``import maya_code_editor`` を実行すると ``ModuleNotFoundError`` になるため、先にロードしてください。
mayapy(standalone)から補完などの Python API を使う場合も同様です。

.. code-block:: python

   from maya import cmds
   cmds.loadPlugin('mayaCodeEditor')   # .mod の MAYA_PLUG_IN_PATH から名前で見つかる
   import maya_code_editor

開き方の指定:

.. list-table::
   :header-rows: 1
   :widths: 35 30 35

   * - MEL
     - Python
     - 動作
   * - ``mayaCodeEditor -show``
     - ``maya_code_editor.show()``
     - 既存の配置を保ったまま開く。初回はフローティング表示。
   * - ``mayaCodeEditor -show -floating false``
     - ``maya_code_editor.show(floating=False)``
     - ドッキングして開く(初回は下側)。
   * - ``mayaCodeEditor -show -floating true``
     - ``maya_code_editor.show(floating=True)``
     - フローティング表示に戻す。

繰り返し ``show()`` や Window メニューを実行すると、既存の本文を一度閉じて同じ画面を開き直します。
未保存のタブ・編集状態・ドッキング位置は保持します。プラグインのアンロードやコードの再読み込みではありません。

初回はフローティング表示です。Maya のドックのタイトル部分をドラッグして、好きな位置へ配置してください。

プラグインの信頼確認
--------------------

Maya が「信頼されていない場所からのロード」の確認を出した場合は、Maya の画面で確認してください。
Maya Code Editor は Security 設定を変更しません。プラグインのフォルダーを信頼済みの場所へ登録するには、
Preferences → Security → Plug-ins の「My trusted plugin locations」に追加します。

更新するとき
------------

* C++ プラグイン(``.mll``)は Python の ``reload()`` では更新されません。Maya Code Editor の Python 部分も ``.mll`` に
  同梱されているため同様です。更新後は Maya を再起動してください。

配置していないバージョンでは
----------------------------

対応する ``mayaCodeEditor.mll`` が ``MAYA_PLUG_IN_PATH`` に見つからない Maya では、Plug-in Manager での
ロードや ``cmds.loadPlugin('mayaCodeEditor')`` が Maya 標準のエラー(プラグインが見つからない旨)になります。
その場合は :doc:`development` の手順でビルドしてください。
