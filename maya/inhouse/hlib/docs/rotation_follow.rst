回転成分の割合追従
==================

``hlib.animation.RotationFollow`` は、入力jointのローカル回転を生成時の姿勢から分解し、
全回転・Twist・Swingのいずれかを指定割合で出力します。Maya標準ノードのみを使います。

.. code-block:: python

   from hlib.animation import RotationFollow

   graph = RotationFollow.create(
       "elbow_jnt", name="elbowFollow", mode="full", axis="x", ratio=0.5,
   )
   # 入力と同じ親空間、TRSとjointOrientがidentityの補助骨へ接続する
   graph.container.plug("matrix").connect("half_jnt.offsetParentMatrix")
   graph.container.plug("ratio").set(0.25)

``mode`` は ``full`` / ``twist`` / ``swing`` 。Twist軸は生成時に指定した ``axis`` です。
``ratio`` は0〜1で、0.5は **入力からの回転差分の半分** を意味します。
180度の回転や、現在値のEuler成分を単純に半分にする処理ではありません。
補間にはQuaternionを用います。全成分は既存 ``SwingTwist`` の分解結果を再構成します。

出力は親空間の行列です。入力jointの ``matrix * offsetParentMatrix`` を使用し、
ワールド行列を経由しません。JointOrientと生成時の回転を基準姿勢として保持します。
回転だけを割合追従し、位置は入力の現在位置を完全に追従します。scaleとshearは出力しません。
別の親空間へ直接接続したり、非identityのTRSへ重ねたりすると二重変換になります。

* ``matrix``: 基準回転に割合追従を適用し、入力の現在位置を合成した行列。
* ``restMatrix``: 作成時の位置と回転。追従停止時の復帰用。
* ``ratio``: 追従割合。DG内でも0〜1へ制限。アニメーション可。
* ``followMode``: 0=Full、1=Twist、2=Swing。成分選択用。

上流の親の動きは、出力先の親階層から通常どおり継承します。
「Twistのみ」は入力jointの親に対する回転差分に適用され、親のSwingまで除去する意味ではありません。
生成後の入力親変更、負・非一様scale、shear、多回転、180度境界の連続性は対象外です。
独自プラグインやフレームごとのPythonコールバックは使用しません。
