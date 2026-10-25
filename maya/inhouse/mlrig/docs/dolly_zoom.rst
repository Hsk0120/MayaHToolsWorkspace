カメラのドリーズーム(DollyZoom)
================================

``mlrig.setups.DollyZoom`` は、カメラと被写体の **視線の方向の距離** から **焦点距離** を決め、カメラを前後に
動かしても **被写体の写る大きさが変わらない** ようにします。被写体の大きさはそのままで背景の遠近感だけが
変わる、いわゆるドリーズーム(めまいの効果)をカメラの移動だけで作れます。

* カメラを被写体へ近づけながら広角にし、背景が後ろへ広がって見える演出を作りたいとき。
* カメラの位置(パース)だけを変えて、被写体の画面の大きさを保ったまま構図を比べたいとき。
* 焦点距離のキーを打たずに、カメラの移動のキーだけで画角を連動させたいとき。

Maya標準ノード(``vectorProduct`` ・ ``plusMinusAverage`` ・ ``multiplyDivide`` ・ ``blendTwoAttr`` ・ ``clamp`` ・
``angleBetween``)だけで組み、containerのアトリビュートへ出力します(既定ではカメラの ``focalLength`` へ接続)。
独自プラグイン、エクスプレッション、フレームごとのPythonは使いません。時刻や前のフレームの結果を使わないので、
どのフレームでも同じ配置からは同じ値になります。生成したノードはcontainerが所有します。

.. code-block:: python

   from mlrig.setups import DollyZoom

   dolly = DollyZoom.create("shotCam", "hero_head_jnt", name="dolly")  # カメラの焦点距離へ接続する
   cmds.setAttr("shotCam.translateZ", 15)       # 近づくと広角になり、頭の写る大きさは変わらない
   cmds.getAttr("dolly.fieldOfView")            # 横の画角(度)
   cmds.setAttr("dolly.weight", 0)              # 作成時の焦点距離へ戻す(0〜1で効きを補間)

式
--

カメラのワールド位置を ``o`` 、カメラの -Z(視線)を正規化した向きを ``n`` 、被写体のワールド位置を ``p`` とすると、
視線の方向の距離は

``depth = (p - o) · n``

です。被写体を通り視線に垂直な面で、画面の横幅に写る範囲の幅は ``W = depth · a / f`` ( ``a`` は横のフィルムバックを
mm に直した値 ``horizontalFilmAperture × 25.4`` 、 ``f`` は焦点距離(mm))なので、 ``W`` を ``frameWidth`` に保つ焦点距離は

``f_zoom = depth · a / frameWidth``

``focalLength = clamp(restFocalLength + weight · (f_zoom - restFocalLength), 2.5, 100000)``

です。作成時の ``frameWidth`` は作成時の距離と焦点距離から求めるので、作成直後の焦点距離は変わりません。
焦点距離と距離の比が一定になるので、フィルムの合わせ方(film fit)によらず被写体の面の写り方全体が保たれます。
横の画角は ``fieldOfView = 2 · atan(a / (2 · focalLength))`` で、 ``angleBetween`` で2つのベクトル
``(f, a/2, 0)`` ・ ``(f, -a/2, 0)`` のなす角として求めます。

containerのアトリビュート
-------------------------

.. list-table::
   :header-rows: 1

   * - 名前
     - 内容
   * - ``weight``
     - ドリーズームの効き(keyable、0〜1)。0で ``restFocalLength`` 、1で距離に比例した焦点距離。
   * - ``frameWidth``
     - 被写体の面で画面の横幅に写る幅(keyable、cm)。小さくすると被写体が大きく写ります。
   * - ``restFocalLength``
     - ``weight`` が0のときの焦点距離(keyable、mm、作成時の値)。
   * - ``focalLength``
     - 焦点距離(出力、mm)。 ``connect=True`` (既定)ならカメラの ``focalLength`` へ接続します。
   * - ``depth``
     - 視線の方向の被写体までの距離(出力、cm、被写体がカメラの後ろなら負)。
   * - ``fieldOfView``
     - 横の画角(出力、度)。

制限
----

* 写る大きさを保つのは被写体の点を通り視線に垂直な面です。被写体より手前・奥のものは距離の比に応じて大きさが変わります。
* 被写体がカメラの後ろへ回る(``depth`` が0以下)と焦点距離はMayaの下限 2.5mm になります。作成時は被写体がカメラの前に
  ある必要があります。
* ``vectorProduct`` ・ ``multiplyDivide`` は単精度で計算するため、焦点距離には相対で1e-7程度の丸めの誤差が入ります。
* カメラのフィルムバックを作成後に変えると、 ``frameWidth`` (幅)を保ったまま焦点距離が変わります。
* containerを削除するとカメラの焦点距離の接続が外れます。外れた後の焦点距離の値は元に戻らないことがあるため、
  必要なら設定し直してください。

試験
----

``mlrig/__tests__/test_setup_dolly_zoom.py`` (``setups`` スイート)で、回転・移動した親の下のカメラと、回転・非一様
スケールした親の下の被写体について、作成直後に焦点距離が変わらないこと、乱数の配置20通りで ``depth`` ・焦点距離が
試験側でワールド配置から独立に計算した値と一致し(相対の許容 1e-6)、被写体の左右に ``frameWidth/2`` ずらした点が
画面の左右の端に写ること、画角が式(許容 1e-5度)とMayaのカメラの横の画角(許容 1e-3度、Mayaの内部の計算の丸め)と
一致すること、 ``weight`` ・ ``frameWidth`` ・フィルムバックの変更、被写体が後ろへ回った場合の下限とカメラのscaleの
影響が無いこと、 ``connect=False`` とカメラのシェイプの指定、container所有とUndo/Redo、引数を確認します。

参考にした考え方
----------------

* Wikipedia「Dolly zoom」(カメラを被写体へ近づける・遠ざけると同時にズームで画角を変え、被写体の大きさを保つ技法)。
* カメラの焦点距離・フィルムバック・画角の関係(Autodesk Maya ヘルプのカメラのアトリビュートの説明にある
  Angle of View と Focal Length の関係)と、被写体の面の幅 ``W = depth · a / f`` を一定に保つ考え方。
