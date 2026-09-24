インストール
============

Maya の実行環境
---------------

このワークスペースには Maya 2022・2024・2025・2026・2027 用の起動バッチがあります。
各機能の対応状況は使用する Maya で確認してください。

インストール
------------

ワークスペースの ``maya/maya_*_en.bat`` から、インストール済みの Maya を起動します。
起動時に ``maya/inhouse`` が Python の検索パスへ追加されます。
Script Editor の Python タブで読み込みます。

.. code-block:: python

   import hlib

変更の反映
----------

読み込み済みの hlib を更新する場合は、既存のラッパーを必要に応じて取得し直します。

.. code-block:: python

   hlib.reload()

ドキュメントの閲覧
------------------

公開版は `hlib ドキュメント <https://hsk0120.github.io/MayaHToolsWorkspace/>`_
から閲覧できます。スマートフォンでもアクセスでき、閲覧する端末にMayaやPythonは不要です。

ローカル版は ``maya/inhouse/hlib/docs/_build/html/index.html`` をブラウザーで開きます。
ソースや docstring の更新後は ``maya/inhouse/hlib/docs/rebuild.bat`` を実行してください。
ローカル版の再ビルドだけでは公開版は更新されません。

GitHub Pagesへの自動公開
----------------------------------------

公開版はGitHub ActionsでSphinxをビルドし、生成したHTMLをGitHub Pagesへ配信しています。
設定ファイルはリポジトリ直下の ``.github/workflows/hlib-docs.yml`` です。

1. ドキュメントの ``.rst``、Pythonのdocstring、表示設定などを変更します。
2. ローカルで ``docs/rebuild.bat`` を実行し、表示とビルド結果を確認します。
3. 変更をコミットしてGitHubの ``main`` ブランチへpushします。
4. GitHub ActionsがPython 3.11と ``docs/requirements.txt`` の依存パッケージを用意し、
   SphinxでHTMLを生成します。APIリファレンスはAutoAPIがPythonソースから静的に生成するため、
   Mayaの起動・インストールや外部submoduleの取得は不要です。
5. ビルド成功後、生成HTMLをPages用artifactとして渡し、``deploy`` ジョブが公開します。
   公開URLは更新前と同じです。

自動実行の対象は ``main`` へのpushのうち、``maya/inhouse/hlib/**`` または
``.github/workflows/hlib-docs.yml`` が変更された場合です。他ブランチへのpush、
ローカル保存・コミットだけでは公開されません。
生成物の ``_build/html`` をGitへコミットする必要はありません。

ビルドは ``-W --keep-going`` を付けて実行し、Sphinxの警告も失敗として扱います。
ビルドに失敗すると新しいHTMLは公開されず、それまでの公開版が残ります。
公開処理には ``pages: write`` と ``id-token: write`` の権限を使用し、
リポジトリの Settings → Pages → Source は ``GitHub Actions`` に設定しています。

実行状況の確認と手動再公開
--------------------------

`Publish hlib documentation <https://github.com/Hsk0120/MayaHToolsWorkspace/actions/workflows/hlib-docs.yml>`_
で実行履歴を確認できます。``build`` と ``deploy`` の両方が成功すると公開完了です。
失敗した場合は該当ジョブを開き、依存パッケージのインストール、Sphinxの警告・エラー、
Pagesへの配信のどの段階で失敗したかを確認してください。

変更をpushせず再公開する場合は、同ページの ``Run workflow`` からブランチに
``main`` を選んで実行します。実行にはGitHubへのログインと必要なリポジトリ権限が必要です。
スマートフォンのブラウザーからも操作できます。
ローカルPC上の未pushの変更は、この操作では取り込まれません。

公開版が古い場合は、まず該当変更が ``main`` に含まれ、そのコミットの公開処理が成功しているかを
確認します。成功後も表示が古ければ、閲覧中のページを再読み込みしてください。
