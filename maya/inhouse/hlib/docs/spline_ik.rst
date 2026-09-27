Spline IK
=========

``hlib.animation.SplineIK`` は既存の骨列とコントロールを使い、
Maya標準の ``ikSplineSolver`` と3次NURBSカーブを生成します。
独自プラグイン、Bifrost、毎フレームのPython実行は不要です。

.. code-block:: python

   from hlib.animation import SplineIK

   graph = SplineIK.create(
       joints, controls, setup_group, name="tailSplineGraph", up_axis="z",
   )
   graph.set_enabled(False)
   graph.set_enabled(True)
   handle = graph.member("handle")

``joints`` は根元から末端までの連続した3本以上のjointです。
ローカルXが長手方向となる、回転入力やキーのない骨を渡してください。
``controls`` は4〜32個の異なるtransformで、順番にカーブのCVを駆動します。
内部CVは通過点ではなく制御点です。コントロールの移動量と骨の移動量は一致しません。
``parent`` はカーブとhandleの親です。parentとcontrolsを計算対象骨列の子に置くと
循環するため拒否します。下流ノードを経由した循環をすべて自動判定するものではありません。

各controlのworldMatrixをカーブの親空間へ変換してCVへ接続します。
Spline IKソルバーへのカーブ入力はworldSpaceであり、完全なローカル空間評価ではありません。
骨長は入力骨のまま維持し、ストレッチは行いません。
両端controlのworldMatrixをAdvanced Twistへ渡します。
``up_axis`` はyまたはzで、骨とcontrolの同軸を上方向として扱います。
接線と上方向が平行な姿勢や多回転での連続性は保証しません。

``set_enabled(False)`` はinCurveを切断し、ikBlendを0、nodeStateをBlockingにします。
既存骨をFK姿勢へ戻す機能ではありません。呼出側で出力経路や基準姿勢を管理してください。
この状態は構成切替用で、連続ブレンドではありません。

``container`` が生成したカーブ、handle、effector、CV変換ノードを所有します。
入力の骨、control、parentは所有しません。生成と有効状態の変更はUndo対象です。
生成物削除後も入力骨は保持されますが、IKで得た最終姿勢が残る場合があります。

Mayaのソルバー仕様は `Autodesk ikHandle command
<https://help.autodesk.com/cloudhelp/2025/ENU/Maya-Tech-Docs/CommandsPython/ikHandle.html>`_
を参照してください。

カーブの近似
------------

``hlib.animation.CurveFit.fit(points, count)`` は、2点以上の3次元点列から
4〜32個のCVを返します。点列の弦長を正規化し、3次clamped均等knotの
最小二乗問題を解きます。NumPy等の外部ライブラリは使用しません。
入出力は同じ空間・単位で、端点を固定し、サンプルが少ない場合は直線配置へ
弱く正則化します。``basis(count, parameter)`` は0〜1パラメータでのCV重みです。

折れ線の長さ、鋭い角、骨回転を完全に復元するものではありません。
Mayaシーンを操作せず、ソルバー評価後の誤差検証と姿勢の採用判断は呼出側で行います。
