テスト方法
==========

実行環境
--------

テストは専用mayapyプロセスで実行します。新規シーンに切り替えるため、
作業中のMaya GUIへテストファイルを送信しないでください。
C++比較には対象Maya用のhrigNodes、Bifrost比較にはhlib_bifrostと対応Bifrostが必要です。
ビルド方法・BifrostのUndo制限は :doc:`constraint_performance` を参照してください。

リポジトリ直下の専用PowerShellで以下を実行し、終了後はそのPowerShellを閉じます。

.. code-block:: powershell

   $testRoot = Join-Path $PWD '.maya-output/hrig-tests'
   New-Item -ItemType Directory -Force "$testRoot/app", "$testRoot/temp" | Out-Null
   $env:MAYA_APP_DIR = "$testRoot/app"
   $env:TEMP = "$testRoot/temp"
   $env:TMP = $env:TEMP
   & 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' tools/test_rig_packages.py --suite setups
   & 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' tools/test_rig_packages.py --suite matrix-plugins
   & 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' tools/test_rig_packages.py --suite native

各コマンドの終了コード0と最終のOKを確認します。2025を検証する場合はmayapyのパスと
テスト用ディレクトリを2025用に変更します。既存GUIのプラグイン再ロードは行いません。

スイートの範囲
--------------

* ``setups``: 行列追従、空間切替、補助骨、回転分解、揺れ物、Spline、伸縮、ポーズ編集など。
* ``matrix-plugins``: C++・Bifrost行列追従。BifrostのUndo/GUI拒否も含みます。
* ``native``: リグ定義とC++バックエンド。
* ``standard``: 標準ノードのリグ・レイヤー統合テスト。
* ``bifrost``: Bifrostグラフとリムのテスト。

全スイート一括実行には複数の依存が必要です。変更範囲に応じて選択してください。
最新のテストファイル構成は ``tools/test_rig_packages.py`` が実体です。

性能比較
--------

.. code-block:: powershell

   & 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' tools/benchmark_hrig_constraints.py --plugins --modes serial parallel --count 300 --frames 120 --repeats 5 --output "$testRoot/results.json"

Cached Playbackは無効化し、各反復直前にも照会します。有効なら中断します。
既定のモードはDG・Serial・Parallelです。Serialは評価グラフの直列評価で、
Bifrost内部も含めたCPU 1スレッド固定ではありません。
JSONに実際のモード・キャッシュ状態・fallback・各反復の秒数・中央値を記録します。

ドキュメントのビルド
--------------------

Maya不要のPython環境で、リポジトリ直下から実行します。

.. code-block:: powershell

   python -m pip install -r maya/inhouse/hrig/docs/requirements.txt
   python -m sphinx -W --keep-going -b html maya/inhouse/hrig/docs .maya-output/hrig-docs

出力の ``index.html`` を開きます。hlibのsphinxdocテーマとCSSを共有するため、
ワークスペース内のhlib/_docsも必要です。外部ツール調査メモや生ログはサイトへ取り込みません。
