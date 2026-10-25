deleteNonDeformerHistory
========================

選んだオブジェクトの作成履歴のうち、デフォーマー(skinCluster・blendShape など)以外の履歴を消すツールです。
Maya の Edit > Delete by Type > Non-Deformer History と同じ処理(``bakePartialHistory -prePostDeformers``)を、選択中のものに行います。

開き方
------

HTools > rigging > deleteNonDeformerHistory。

画面
----

画面はありません。選ぶとすぐに処理します。

使い方
------

1. 履歴を整理したいメッシュなどを選びます(複数可)。
2. メニューから選びます。
3. デフォーマーより前・後ろにあるモデリングの履歴(polyBevel・polySmooth など)が焼き込まれて消え、デフォーマーは残ります。
   スキンのウェイトはそのままです。

.. list-table::
   :header-rows: 1
   :widths: 50 50

   * - 実行前
     - 実行後
   * - .. image:: ../_static/images/rigging/deleteNonDeformerHistory_before.png
          :alt: ノードエディター。polyCylinder・polyBevel・polySmoothFace・skinCluster・polyMoveVertex がメッシュの履歴に並んでいる
     - .. image:: ../_static/images/rigging/deleteNonDeformerHistory_after.png
          :alt: 実行後のノードエディター。arm_geoShapeOrig から skinCluster1 を通って arm_geoShape へつながるだけになっている

上の例では、スキンの前の polyCylinder・polyBevel・polySmoothFace と、スキンの後ろの polyMoveVertex が消え、
skinCluster だけが残りました。

注意・制限
----------

- 何も選ばずに実行すると何もしません(警告も出しません)。
- 選んだものに順に実行します。ジョイントなどシェイプを持たないノードが含まれると ``Select one or more shapes.`` のエラーで止まります
  (それより前に選んだものは処理済みです)。
- 消した履歴は Undo で戻せます。複数選んだ場合は、オブジェクトごとに1回ずつ Undo が必要です。
