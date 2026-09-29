テスト結果
==========

2026年9月29日の実装済み拘束バックエンドの検証記録です。
このページはその時点の結果であり、将来の変更に対する自動更新・速度保証ではありません。

Serial / Parallelの実測
--------------------------

Maya 2027、Windows 11、Intel64 Family 6 Model 151 Stepping 2、論理CPU20、Mayaスレッド設定20。
Bifrostは ``3.0.0.0-202602040323-9df3db7`` です。
300拘束、120フレーム×5回の中央値を示します。単位はms/frameで、小さいほど高速です。
詳しいシーンと測定範囲は :doc:`test_scenes` を参照してください。

.. list-table:: 評価時間（ms/frame）
   :header-rows: 1

   * - 構成
     - 独立 Serial
     - 独立 Parallel
     - 階層 Serial
     - 階層 Parallel
   * - parentConstraint
     - 8.813
     - 2.393
     - 9.441
     - 9.782
   * - 行列＋decompose
     - 6.532
     - 2.193
     - 7.086
     - 6.601
   * - 行列→OPM
     - 4.685
     - 1.909
     - 4.682
     - 2.791
   * - C++
     - 4.731
     - 1.962
     - 4.763
     - 2.931
   * - Bifrost
     - 26.301
     - 18.228
     - 26.555
     - 25.577

全20計測条件でCached Playback無効、要求した評価モードとの一致、fallbackなしを確認しました。
小規模の40姿勢条件も誤差1e-6以内で一致し、専用mayapyは終了コード0でした。
生データはローカルの ``.maya-output/constraint-benchmark/serial-parallel/results.json`` にあります。
生ログ・研究メモは公開サイトやGitへ含めません。

今回の単純な行列追従では標準OPMが最速でした。Bifrostは独立配置では並列評価で短縮しましたが、
1拘束1GraphShapeという構成では標準OPMより長い時間を要しました。
グラフ境界の固定費は候補であり、内部プロファイルで原因を確定した結果ではありません。
Boardや配列一括処理へ変更した場合の性能は未測定です。

機能テストの記録
----------------

同日のC++/Bifrost追加時に、Maya 2025・2027の両版で以下の結果を確認しています。
今回のドキュメント整備でこれらのMayaテストを再実行したものではありません。

.. list-table:: 既存実行ログによる検証記録
   :header-rows: 1

   * - スイート
     - Maya 2025
     - Maya 2027
   * - setups
     - 47件成功
     - 47件成功
   * - matrix-plugins
     - 17件成功
     - 17件成功
   * - native
     - 7件成功
     - 7件成功

証跡はローカルの ``.maya-output/constraint-benchmark/final2025-*.log`` と
``final2027-*.log`` です。2025の大規模5構成性能比較は未実施です。

既知の制限
----------

* Bifrostグラフ構築のUndo/Redoで専用Mayaが異常終了したため、現在はGUIまたはUndo有効時の構築を拒否します。
  テスト成功にはこの拒否の確認が含まれ、BifrostのUndo/Redoが動作することを示しません。
* 単一入力の剛体追従の検証です。複数入力、軸スキップ、jointOrientなどのparentConstraint全機能は対象外です。
* キャラクター全体、描画、スキニング、CPU 1スレッド固定、Bifrost内部の時間内訳は未測定です。
* 環境負荷やMaya・Bifrostの版によって数値は変わります。比較時は同じ実行内で全構成を再計測してください。
