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
