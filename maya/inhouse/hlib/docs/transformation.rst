変換情報の保存と復元
======================

``hlib.maths.Transformation`` は、移動・回転・スケールに加えて、Mayaの補助成分を
保持する可変の値です。シーン内のノードへの参照は持ちません。
各成分には既存のOpenMaya派生の数学型を使いますが、Transformation自体は
それらをまとめたクラスであり、MTransformationMatrixの派生ではありません。

保存と復元
------------

.. code-block:: python

   import hlib

   joint = hlib.getNode("neck_IK_jnt")
   saved = joint.getTransformation()

   # 必要な編集の後、補助回転・回転順序も含めて復元する。
   joint.setTransformation(saved)    # 戻り値はjoint自身。

``getTransformation()`` はチャンネル値を直接取得します。Euler回転の375度などの周期や
スケールの符号も、行列への分解を挟まずに保持します。
``rotateAxis`` と ``jointOrient`` はQuaternionで保持するため、それらのEuler表現の
周期は保持しません。適用時は現在のチャンネル値に近いEuler解を使います。
入力のTransformationは適用しても変更されません。

保持する成分
--------------

.. list-table::
   :header-rows: 1

   * - 長名
     - 短縮名
     - 型
   * - translate
     - t
     - Translation
   * - rotate
     - r
     - EulerRotation
   * - quaternion
     - q
     - Quaternion（rotateと同期）
   * - scale / shear
     - s / sh
     - Scale / Shear
   * - rotateOrder
     - ro
     - int（0〜5）
   * - rotateAxis / jointOrient
     - ra / jo
     - Quaternion
   * - rotatePivot / rotatePivotTranslate
     - rp / rpt
     - Translation
   * - scalePivot / scalePivotTranslate
     - sp / spt
     - Translation
   * - inverseScale
     - ``is_``
     - Scale
   * - segmentScaleCompensate
     - ssc
     - bool
   * - matrix
     - m
     - Matrix（成分から毎回合成）

距離はcm、角度はradianです。UIの単位設定には依存しません。
値だけを作った場合のSSCはTrue、inverseScaleは(1, 1, 1)です。
Transformノードから取得する場合、SSCはFalseになります。

.. code-block:: python

   from hlib.maths import Transformation, EulerRotation, Matrix

   value = Transformation(t=(1, 2, 3), ro=0, r=(0, 0.5, 0), s=(1, 1, 1))
   edited = value.copy()           # 各成分も独立したコピー
   edited.t.y += 2                # 値の編集だけ。シーンは変化しない。
   edited.ra = EulerRotation(0.1, 0, 0)
   matrix = edited.m
   restored = Transformation(matrix)

``Transformation(matrix)`` は行列の分解です。元のピボットやjointOrient、Eulerの周期は
行列から一意に復元できないため既定値になります。
``Transformation(existing)`` は補助情報を含む独立コピーです。
``om2.MTransformationMatrix`` からは、その型が保持するピボットや回転軸も取り込みます。

既存の値の ``m`` へ行列を代入すると、補助成分を保持してTRSとシアーを求め直します。
回転順序と可能なスケール符号を保持し、Euler解は現在値に近づけます。
``ro`` の変更は姿勢を保ってEuler表現を並べ替えます。
各成分は可変で、直接編集できます。値全体はハッシュ不可です。
``isEquivalent`` は全成分を比較し、姿勢だけの比較には ``a.m.isEquivalent(b.m)`` を使います。

ワールド空間と対象ノードへの適合
----------------------------------

.. code-block:: python

   world = source.getTransformation(ws=True)
   planned = target.setTransformation(world, ws=True, get=True)  # シーンを更新せず設定予定値を返す
   target.setTransformation(world, ws=True)

``ws/worldSpace`` に対応します。親行列とoffsetParentMatrixを考慮し、参照している
DAGインスタンスのパスに従います。offsetParentMatrixそのものは書き換えません。
``value * matrix`` は変換を後乗算した新しい値を返し、translateと回転ピボット位置も変換します。
ワールド変換では行列分解が必要なので、元のローカルEuler値の完全な数値一致は保証しません。
負スケールとピボットがある場合も、元のtranslate位置を変換先へ移します。
行列だけではチャンネル値が一意に決まらないため、等価な姿勢でも値が異なることがあります。

ジョイントへの適用では、対象のinverseScaleとその接続を保持し、ピボット系成分を除いた
条件で行列を合わせます。Transformへの適用ではjointOrient・SSCを除いて合わせます。
したがって、異なる種類のノードや異なる親へ適用した場合は、各チャンネル値が変わることがあります。
``get=True`` の結果はその適合後のローカルTransformationです。

``safe=True`` は書けない成分を残し、実際に適用できた補助成分を使ってTRSを計算します。
TRS自体にもロックや入力接続がある場合、目的の行列との一致は保証されません。
通常の適用は一回のUndoで戻せます。処理途中の例外による完了済みの変更は自動で戻しません。

制限と既存API
----------------

- 制約ノードの再接続、キー・接続・ロックの保存は行いません。コンストレイントが駆動中の
  チャンネルへ適用する場合、その入力接続の処理は別途必要です。
- 行列分解できないゼロスケールや、特異・極端に縮小された親行列へのワールド適用は拒否します。
  値としてのゼロスケールの保持とローカル合成は可能です。
- ``Matrix.asTransformation()`` は ``hlib.maths.Transformation`` を返します。
  ``Transformation(matrix)`` でも変換できます。OpenMaya型が必要な場合は
  ``om2.MTransformationMatrix(matrix)`` を使います。
- ``setMatrix(get=True)`` の辞書返却は変わりません。
  ``Matrix(value)``、``Matrix.fromTransformation(value)``、``MatrixPlug.set(value)`` は
  Transformationを受け取り、合成行列を使います。ピボット等の成分情報は行列には保存されません。
- ``Transforms`` / ``Joints`` でもgetTransformation/setTransformationを利用できます。get=Trueの一括適用は
  対象ごとの設定予定Transformationのリストを返します。
