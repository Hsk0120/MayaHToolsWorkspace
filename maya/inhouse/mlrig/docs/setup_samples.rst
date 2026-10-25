メニューのセットアップ例(Setup Samples)
==========================================

上部の **mlrig** メニューの **Setup Samples** から、``mlrig.setups`` の各セットアップを
小さな入力つきで現在のシーンへ作り、すぐに動かして試せます。実体は
``mlrig.setupSamples.SetupSamples`` で、メニューの項目は ``Menu.run("setup:<種類>")`` を呼びます。

- 新規シーンは作りません。``<種類><番号>_sample_grp`` の下に入力をまとめ、名前は既存のノードと
  重ならない連番にします。
- 1回のUndoでサンプル全体を取り消せます。
- 作成後は「動かす対象」(ikHandle・入力のjoint・containerなど)を選択します。
- 入力は既定の色、セットアップの出力を受けるjoint・locatorは緑で表示します。出力は
  ``offsetParentMatrix`` で受けるため、作成直後は入力と重なります(WaveChainは波が見えるよう
  振幅20度で作るので、最初から入力とずれます。WaveFloatも振幅を入れて時刻へ接続するので、最初から入力とずれます)。

.. list-table::
   :header-rows: 1
   :widths: 30 25 45

   * - 項目
     - 選択される対象
     - 試し方
   * - HingeIK - offset knee leg
     - ikHandle
     - 移動すると、膝が横にずれた脚でも膝は1軸だけで曲がる。
   * - PlanarIK - leg with offset bones
     - ikHandle
     - 移動すると、途中にずれた骨がある元の脚がIK用チェーンに追従する。
   * - PoleVectorPlacement - arm
     - 肘のjoint
     - 回すと、緑のlocator(ポールベクターの位置)が肘の外側へ移る。
   * - NoFlipPole - leg with foot-driven knee
     - 足のコントロールのlocator
     - 動かす・ ``rotateY`` で回すと、ポール(緑のlocator)が足の前の向きに付いて動き、膝がその向きへ曲がる。足を股関節の前後へ大きく振っても膝は反転しない。containerの ``kneeTwist`` で脚の軸まわりに膝の向きを回せる。
   * - LimbPin - arm with elbow pin and slide
     - 肘の位置の極ベクトルの操作子(locator)
     - 動かすと、pin=1 なので肘(緑)が操作子の位置へ留まり、上腕と前腕の長さが変わる。手首の目標(locator)を動かすと前腕の長さが変わる。containerの ``pin`` を0へ下げると元の長さへ戻り、 ``slide`` で上腕と前腕の長さの比が変わる(合計は同じ)。
   * - EyelidFollow - eye and lids
     - 目のjoint
     - 回すと、上下のまぶた(緑)が追従する。containerの ``blink`` などで調整する。
   * - JawHinge - jaw
     - 顎のjoint
     - rotateXを回すと、閉じ側は柔らかく止まり、開くと前へずれる。
   * - Piston - cylinder and rod
     - アームのtransform
     - 回すと、シリンダーとロッド(緑)が互いを向く。containerの ``overStroke`` で範囲外を確認する。
   * - BowString - bow and nock
     - ノックのlocator
     - +Z方向へ引くと、弦(緑)がノックへ向かって伸び、containerの ``drawWeight`` が0から1へ増える。
   * - WaveChain - tail wave
     - container
     - ``phase`` を変えると、波が根元から先へ進む。
   * - WaveFloat - boat on waves
     - 船のコントロール(locator)
     - 再生すると、船(緑)が2つの波に乗って上下・前後に揺れて傾く。水平に動かすと、その場所の波に乗る。
   * - WheelRoll - wheel
     - 車体のtransform
     - Z方向へ動かすと、車輪(緑)が移動量に合わせて回る。
   * - GearTrain - four gears
     - 駆動側の歯車のjoint
     - ``rotateZ`` で回すと、歯数の比(24:12、同じ軸、20:10)で緑の歯車が逆向き・同じ向きに回る(十字の先が歯車の半径)。containerの ``teeth0`` 〜 ``teeth3`` で歯数、 ``phase1`` 〜 ``phase3`` で歯の合わせを変えられる。
   * - AckermannSteering - car front wheels
     - ハンドルのjoint
     - ``rotateZ`` で回すと(比 -1/8)、緑の左右の前輪がアッカーマンの幾何で内輪を外輪より大きく切る(十字の先が車輪の半径、短い先が車軸の向き)。containerの ``ackermann`` を0にすると左右が同じ角度になる。
   * - TreadBelt - tank tread
     - 車体のtransform
     - ``translateZ`` で前へ動かすと、長円の曲線の上の16枚の板(緑)が巡回し、地面側の板はその場に止まるように回る。containerの ``phase`` で全体をずらせる。
   * - RockerRoll - rocking chair runner
     - container
     - ``roll`` を変えると、円弧の脚(緑)の接地点が円弧の上を移り、底が滑らずに前後へ転がる。 ``radius`` で円弧の半径を変えられる。
   * - OutlineBank - box tilting on its base outline
     - コントロールのlocator
     - ``rotateX`` ・ ``rotateZ`` を回すと、箱(緑)が傾けた側の底の縁(正方形の輪郭の曲線の上の点)を支点に傾く。containerの ``pivot`` が支点、 ``reach`` で角への寄り方を変えられる。
   * - CrankSlider - engine crank and piston
     - クランクのjoint
     - ``rotateZ`` で回すと、長さ6のロッド(緑)がクランクのピンに付いたままピストンへ向き、ピストン(緑)がY軸に沿って上下する。containerの ``rodLength`` でロッドの長さを変えられる。
   * - ScissorLift - three-stage scissor lift
     - container
     - containerの ``height`` を変えると、3段のX字の腕(緑、先の子jointが腕の反対の端)が真ん中で交わったまま開閉し、台(緑、上)が上下し、右の滑る足(緑)が左右へ動く。
   * - CableSag - hanging cable between two posts
     - 右の留め具のlocator
     - ``translateX`` で左へ近づけるほど、2本の柱の間のケーブルの9点(緑)が深く垂れ、containerの ``length`` (既定9.6)以上離すと一直線に張る。
   * - RotationMinimizingFrames - points
     - 点のlocator
     - 点を動かすと、ねじれを抑えた向き(緑)が点列に沿って付く。
   * - RotationMinimizingFrames - curve
     - 曲線
     - CVを動かすと、曲線の接線に沿った向き(緑)が付く。
   * - Ribbon - five controls
     - 中央のコントロール(locator)
     - 動かす・回すと、帯(テンプレート表示)とその上の7つの向き(緑)が付いてくる。containerの ``width`` ・ ``position<番号>`` も試せる。
   * - ChainNet - fin with two master chains
     - 親チェーンAの2つ目のjoint
     - ``rotateZ`` で回すと、間の3本の子チェーン(緑)が containerの ``bias0`` 〜 ``bias2`` (0.25・0.5・0.75、Bの動きを使う割合)で付いてくる。親チェーンBを回しても同様。子チェーンの節はそのまま手付けで回せる。
   * - LeafJoints - squash arm for export
     - 肘のjoint
     - ``scaleY`` ・ ``scaleZ`` を変えると、書き出し用の肘の葉のjoint(緑)だけが太り、枝のjointと手首・手の先の葉(緑)は scale 1 のまま腕に付いてくる(作成時の肘は scale 0.8・1.6・1.6)。
   * - BodyProportion - body shape parameters
     - container
     - ``armLength`` ・ ``shoulderWidth`` ・ ``legLength`` ・ ``armThickness`` を変えると、体格調整用の骨(緑)の移動・スケールが標準の体格から変わる(-1〜1、太さは-1〜2でclamp。負の側は短く・細くする別の量)。
   * - MetaSpread - palm metacarpals
     - 小指側の中手骨のjoint
     - 回すと、間の2本の中手骨(緑)が1/3・2/3の割合で付いてくる。人差し指側を回しても同様。
   * - NeckHeadSplit - head control shared by the neck
     - 頭の前の円のコントロール
     - 回すと、回転が首の3つの関節へ1/4ずつ分かれて首(緑)がしなり、頭(緑)はコントロールと同じ向きになる(灰色は元の首と頭)。containerの ``weight0`` 〜 ``weight2`` で首の各関節の割合を変える。
   * - FootRoll - reverse foot
     - container
     - ``roll`` を負にするとかかと、正にすると母指球、30度を超えるとつま先を支点に足(緑)が転がる。 ``bank`` で内外の縁を支点に傾き、 ``swivel`` ・ ``toeTap`` も試せる。足のコントロール(locator)を動かすと足全体が付いてくる。
   * - MuscleBulge - biceps
     - 肘のjoint
     - ``rotateZ`` で曲げると、上腕の中央の補助骨(緑)が60度から膨らみ始め、140度で最大になり、少し外(+Y)へ押し出される。ひねり( ``rotateX`` )だけでは膨らまない。
   * - PumpUp - amplify the biceps helper
     - pumpのlocator
     - 上へ動かす( ``translateY`` = pump)と、肘の曲げで膨らむ補助骨(既定の色、MuscleBulge)を増幅した骨(緑)が太くなる。肘の ``rotateZ`` を曲げた状態では、補助骨の膨らみの変化も1.5倍ずつ増える。pumpが0なら2つは一致する。
   * - GroundTilt - four feet
     - 左前足のlocator
     - 上下すると、胴体(緑)が4本の足の面に合わせて傾き、平均の高さの変化だけ上下する。胴体のlocatorを動かす・回すと付いてくる。containerの ``tilt`` ・ ``height`` も試せる。
   * - CenterOfMass - stick figure balance
     - 背骨のjoint
     - ``rotateX`` で前へ倒すと、全身の重心(緑、 ``_comOut``)が前へ移り、床への投影(緑、 ``_floorOut``)が両足首の間から外れて containerの ``balance`` が増える。腕・脚のjointを回しても重心が動く。containerの ``mass<i>`` で体節の重さを変えられる。
   * - SkirtLegOffset - skirt and two legs
     - 左の股関節のjoint
     - ``rotateX`` を負にして脚を前へ上げると、脚に近い前側のスカートの骨(緑)が脚から離れる向きへ開き、後ろの骨は動かない。 ``rotateZ`` で横へ開くと横の骨が開く。containerの ``clearance`` ・ ``maxAngle`` ・ ``spread`` ・ ``weight`` も試せる。
   * - LipZip - sticky lips
     - container
     - ``zipLeft`` ・ ``zipRight`` を0から上げると、左・右の口角に近い組から順に上唇・下唇(緑)が閉じ合わさる。 ``meetHeight`` で合わさる高さ、 ``falloff`` で閉じる途中の幅を変えられる。入力のlocatorを動かすと付いてくる。
   * - SquashBox - four sides
     - container
     - ``top`` ・ ``bottom`` ・ ``outer`` ・ ``inner`` を正にするとその辺が外へ伸び、負にすると潰れる(反対の辺は動かない)。出力(緑、子jointが箱の角)は ``volume`` の割合で直交する向きが細く・太くなる。箱の基準のlocatorを動かすと付いてくる。
   * - PlaneCollision - soft floor
     - 足のコントロールのlocator
     - 下げると、出力(緑)が床から ``radius`` + ``softness`` (1.5cm)の高さで柔らかく止まり始め、少し傾いた床(locator)より下へは沈まない。床を回す・動かすと面が付いてくる。containerの ``softness`` を0にすると硬く止まる。
   * - SpaceBlend - world, chest and hand
     - 手の空間のlocator
     - 動かすと、worldと手の空間に半分ずつ追従する出力(緑)が、手の動きの半分だけ付いてくる。containerの ``weight0`` (world)・ ``weight1`` (胸)・ ``weight2`` (手)を変えると、割合に応じて追従先が混ざる(作成時の位置からは跳ねない)。
   * - CameraAngleReader - face and camera
     - カメラのlocator
     - 頭(正面は+Z)の周りに動かすと、頭の前・左・右・上・下・後ろに置いた緑のlocatorの大きさ(その方向の重み)が連続に移り変わる。重みの和は常に1。containerの ``yawRange`` ・ ``pitchRange`` ・ ``backFade`` で重みが1になる角度を変えられる。
   * - DollyZoom - camera keeps the subject size
     - カメラのtransform
     - ``translateZ`` で前後に動かすと、カメラの焦点距離(containerの ``focalLength``)が被写体までの距離に比例して変わる。カメラから覗く(Panels > Perspective)と、被写体と緑のjointの幅(画面の横幅)はそのままで、奥の柱の広がりだけが変わる。containerの ``weight`` を0にすると元の焦点距離、 ``frameWidth`` で写す幅を変えられる。
   * - OverShoulderCamera - conversation shot
     - 奥の人物の頭のjoint
     - 動かすと、手前の人物の肩越しのカメラ(緑のjoint)が付いていき、カメラから覗く(Panels > Perspective)と奥の人物の頭は画面の右上の三分割の位置に写る。カメラは2人を結ぶ線の同じ側に留まる。containerの ``side`` を -1 にすると反対側、 ``angle`` ・ ``distance`` ・ ``height`` ・ ``screenX`` ・ ``screenY`` で構図を変えられる。
   * - LiveMirror - mirror left arm pose to the right
     - 左の肩のjoint
     - 左の肩・肘・手首を回すと、右の緑のjointがキャラクターのルートのYZ面で鏡に映した姿勢(Behavior)へ付いてくる。ルート( ``liveMirror<番号>_root`` )を動かす・回すと対称面も一緒に動く。右のjointの ``rotate`` 等は空いていて鏡像の上に上乗せできる。containerの ``weight`` を0にすると右は作成時の姿勢へ戻る(肘・手首は ``_elbowMirror`` ・ ``_handMirror`` のcontainer)。
   * - EyeHighlight - catchlight follows the camera
     - カメラのlocator
     - 動かすと、左右の眼球(球のjoint)の表面の緑のハイライトが、カメラと光( ``_light`` のlocator)の中間の向きの点へ移る。眼球を回してもハイライトはカメラ・光から見た位置に留まる。containerの ``follow`` を0にすると瞳の中心( ``_leftPupil`` )の位置に留まり、 ``radius`` で眼球の表面からの距離を変えられる(右目は ``_rightHighlight`` のcontainer)。
   * - UnevenGround - feet and hips on a slope and a step
     - 左足の下の地面のlocator
     - 上下・回転すると、左足(緑の ``_leftFootOut`` )が地面の高さと傾きに載って付いてくる。腰(緑の ``_hipsOut`` )は低い方の足の地面に合わせて下がる。足のlocator( ``_leftFootCtrl`` ・ ``_rightFootCtrl`` )は平らな床の上の動きで、動かすとその位置の地面の高さで載り直す。containerの ``height`` ・ ``align`` ・ ``hips`` で補正の割合、 ``floorHeight`` で床の高さを変えられる。
   * - HipSwing - swing the hips, keep the chest
     - 振りのコントロールのlocator( ``_swingCtrl`` 、背骨の根元の位置)
     - 回すと、緑の腰( ``_hipsOut`` )と脚だけがコントロールの位置を支点に振れ、緑の背骨・胸・首( ``_spineOut`` )は傾かずに元の向きを保つ。containerの ``stabilize`` を0にすると上体も腰と一緒に回り、 ``swing`` で振りの割合を変えられる。COG( ``_cog`` のlocator)を動かすと全体が付いてくる。
   * - BoxRoll - box tumbles edge over edge
     - BoxRoll のcontainer
     - ``roll`` を変えると、緑の箱( ``_boxOut`` )が前の下の縁を支点に傾き、90度を超えると支点が次の縁へ移って縁から縁へ転がる。底は床へ潜らず、90度ごとに平らに着く。containerの ``step`` ・ ``travel`` で何段転がったかと進んだ距離が分かる。
   * - UiSlider - face panel slider
     - 枠の中のコントロール
     - 枠(テンプレート表示の正方形)の中で動かすと、周りの8つの緑のlocatorの大きさ(その方向・角の重み)が変わる。コントロールは枠の外へ出ない。
   * - ComboWeight - smile combo corrective
     - 左の口角のlocator
     - 作成時は右の口角(locator)を上げてあり、口の真ん中の補助骨(緑のjoint)が半分上がる。左の口角の ``translateY`` を 0〜1 で上げると、補正しない場合(赤のlocator)は真ん中が口角の高さまで上がるが、組み合わせのウェイト ``both`` (上の左の緑のlocatorの大きさ)で戻す分を足すので、両方を1にすると緑の骨は元の高さへ戻り、口角だけが上がった形になる。上の右の緑のlocatorは左のウェイトが0.5で最大になる途中のウェイト ``leftHalf`` 。
   * - VirtualChain - flat tail controls as FK
     - 根元のコントロール(locator)
     - 同じ親の下に兄弟として並べた4つのコントロールを、仮想のFK階層でつないである。根元を回すと先のコントロールと中の緑の骨がすべて付いてくる(アウトライナー上は平らなまま)。containerの ``follow1`` 〜 ``follow3`` を0にすると、そのつなぎだけ前を追わなくなる。
   * - StickyControl - control on a skinned surface
     - 下のjoint
     - 回すと2本のjointでスキンした平面が曲がり、表面に貼り付いた緑のコントロールが同じ場所に付いていく。コントロール自体も表面の上で動かせる。
   * - FkIkChain - tail FK/IK blend
     - IKの先端のコントロールのlocator
     - 動かすと、Spline IKの尻尾が曲がり、FK(まっすぐのjoint)とIKを ``blend`` =0.5で混ぜた出力(緑)が中間の弧を描く(節の間の長さは保たれる)。containerの ``blend`` を0にするとFKだけ、1にするとIKだけに一致し、FKのjoint・IKのlocatorの表示が ``fkVisibility`` ・ ``ikVisibility`` で切り替わる。
   * - SlidingFk - tail with two sliding controls
     - 1つ目のコントロールのlocator
     - ``rotateZ`` を回すと、containerの ``position0`` (0.25)の近くの節へ回転が分かれ、出力(緑)の尻尾がその辺りで曲がる。 ``position0`` を変えると曲がる場所がチェーンに沿って移り、 ``falloff0`` で曲がる範囲の広さが変わる。2つ目のコントロールは ``position1`` (0.75)の辺りを曲げる。
   * - SwingLimit - shoulder
     - 入力のjoint
     - 回すと、楕円の範囲で柔らかく止まった向き(緑)になる。
   * - AsymmetricSwingLimit - shoulder
     - 入力のjoint
     - 回すと、向きごとに上限の違う範囲で止まる。
   * - TwistLimit - forearm
     - 入力のjoint
     - rotateXでねじると、-45〜45度で柔らかく止まる。
   * - SwingTwist - swing only
     - 入力のjoint
     - 回すと、ねじれを除いたSwingだけの向き(緑)になる。
   * - RotationFollow - half rotation
     - 入力のjoint
     - 回すと、回転の半分だけ追従する。
   * - ConeReader - shoulder cone
     - 上腕のjoint
     - 回すと、containerの ``weight`` がコーンとの一致度に応じて1から0へ変わる。

スクリプトから作る場合:

.. code-block:: python

   from mlrig.setupSamples import SetupSamples

   sample = SetupSamples.build("hingeIK")
   print(sample.root, sample.target, sample.container)

試験は ``mlrig/__tests__/test_setup_samples.py`` で、全項目について作成・対象の操作による
出力の変化・作成直後の出力と入力の一致・Undo/Redo・名前の連番・``Menu.run`` 経由の実行を確かめます。
メニューの表示そのもの(``cmds.menuItem``)はGUIでのみ作られるため、mayapyの試験では扱いません。

制限:

- サンプルの寸法はcm・度を前提にしています。
- AutoClavicleなど、作業中のセットアップは含めていません。項目を足すときは
  ``SetupSamples.ITEMS`` と試験の ``CHANGES`` を一緒に更新します。
