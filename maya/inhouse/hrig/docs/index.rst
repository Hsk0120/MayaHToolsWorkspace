hrig ドキュメント
==================

Maya 2025以降向けのレイヤードリグ検証パッケージです。
標準ノードを既定とし、hlibを基礎ライブラリとして利用します。
C++・Bifrostは明示選択する比較検証用バックエンドです。

.. toctree::
   :maxdepth: 2
   :caption: テストと計測

   testing
   verification_video
   test_scenes
   test_results
   constraint_performance
   exprespy_comparison

.. toctree::
   :maxdepth: 1
   :caption: 実装済みセットアップ

   space_switch
   twist_distribution
   bend_correction
   swing_twist
   rotation_follow
   root_direction_limit
   aim_axis_conversion
   radial_weights
   secondary_motion
   spline_ik
   length_compensation
