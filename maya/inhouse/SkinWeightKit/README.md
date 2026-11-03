# Skin Weight Kit

メインウィンドウの右端に、独立した縦の領域としてドックする、スキンのウェイト作業用のパネルです。
処理は mlib だけで書き(`skinWeightKit.core`、Qt・maya.cmds を使わない)、画面は PySide(`skinWeightKit.ui`)です。
workspaceControl・optionVar・Maya の Paint Skin Weights ツールの起動は、mlib が持たない画面側の操作なので `ui` で cmds を使います。

頂点を選んで値を入れる操作を中心にし、Paint Skin Weights ツールを開かずにウェイトを整えられるようにしています。

## 起動

- HTools > rigging > skinWeightKit、またはスクリプトの `import skinWeightKit; skinWeightKit.toggle()` で表示・非表示を切り替えます。
- `maya/modules/SkinWeightKit.mod` が有効なら、前回表示していた場合だけ Maya GUI の起動後に自動で表示します。

## 対象

- 頂点・エッジ・フェースを選ぶと、その頂点を対象にします(エッジ・フェースは頂点に直します)。
- メッシュを選ぶと、そのメッシュ全体を対象にします(Prune・Limit・Round・Normalize・Select Bad は全頂点に効きます)。
- 複数のメッシュにまたがる選択は、最初のメッシュだけを使います。
- ジョイントだけを選ぶと、対象のメッシュはそのままで、そのジョイントがアクティブなインフルエンスになります(ビューポートでジョイントをクリックして切り替えられる)。パネルの先頭に対象のメッシュ・skinCluster・頂点の数を出します。

## 機能

| セクション | 内容 |
| --- | --- |
| Influences | インフルエンスの一覧。検索・選んだ頂点で使っているものだけの表示・ロック・選んだ頂点での平均の値(棒と数値)。見出しのクリックで名前・ウェイトの順に並べ替え。クリックでアクティブ、ダブルクリックで影響する頂点を選択。右クリックでアクティブとの間のウェイトの移動・ランプ、全インフルエンス・選んだ頂点に影響するインフルエンスの選択、他を全部ロック・全部のロック/解除・ジョイントの選択・選んだジョイントの追加・親へ移して外す |
| Vertex Table | 選んだ頂点ごとの各インフルエンスの値の表(既定は閉じる)。セルを書き換えるとその頂点の値を変え、同じ列の複数のセルを選んでいれば全部に入れる。合計が1でない行は赤、最大数を超えた行は黄 |
| Select | Grow・Shrink、エッジの Loop・Ring、アクティブなインフルエンスの値が範囲内の頂点を選ぶ Select by Weight |
| Weight | Flood(メッシュ全体、または選んだ頂点をアクティブな値にする)、0〜1 のプリセット(クリックで設定、Shift で加算、Ctrl で減算)、Add/Scale と量で `-`・`+`、値を入れて Set、Paint(Maya の Paint Skin Weights ツールをアクティブなインフルエンスで開く) |
| Brushes | 独自のブラシ(Maya のユーザーペイント artUserPaintCtx を使い、プラグインは作らない)。Smooth(Smooth セクションの方法・半径・最大数を使う)・Sharpen(隣の平均から遠ざけて境目をくっきりさせる)・Remove(アクティブを減らす)・Add(アクティブを増やす)・Transfer(From のインフルエンスからアクティブへ移す)。ブラシの大きさ・強さは Maya の Tool Settings。1ストロークが1回の Undo |
| Blend | Slide(ドラッグでアクティブなインフルエンスを増減。ソフト選択が有効なら減衰に比例。離すと1回の Undo)、Soft Selection to Weight(ソフト選択の減衰をそのまま値にする)、Ramp to...(アクティブから選んだインフルエンスへ、2本のジョイントを結ぶ線に沿って配分。Linear/Smooth)、Deformer to Weight(cluster・softMod・deltaMush 等のデフォーマーのウェイトをアクティブなインフルエンスの値にする) |
| Smooth | Hammer(隣の頂点の平均にする)、Average(選んだ頂点をそろえる)、Smooth(強さと回数で隣へ近づける。隣への重みは Uniform=単純平均・Distance=辺の長さの逆数・Cotangent=三角形の角度から求める形に沿った重み。Gap Radius で辺でつながっていない近くの頂点も含め、Keep max で最大数を保つ)、Shell Average / Shell Rigid(つながったパーツごとに平均、または最大の1つへ100%。鎧の板などの硬いパーツ用) |
| Copy / Mirror | Sample で見本の頂点を覚え、Average(見本の平均)・Proximity(距離の2乗の逆数で重み付けした平均)で選んだ頂点へ配る。Hold で全体を覚え、Fetch で1回の Undo で戻す。頂点のウェイトのコピー(複数なら平均)と、選んだ頂点への貼付け(インフルエンスは名前で対応)。軸と向きを選んだ全体のミラー、Mirror Selected(選んだ頂点だけを位置で反対側の頂点へ写し、インフルエンスは名前の左右 `L_`/`R_`・`_l`/`_r`・`Left`/`Right` 等で入れ替える) |
| Cleanup | Prune(しきい値未満を0)、Limit(1頂点の最大数)、Round(小数の桁)、Normalize、Select Bad(合計が1でない・最大数を超えた頂点を選ぶ) |
| Game Cleanup | ゲームエンジン向けのリダクション。頂点ごとに、しきい値未満を0 → 大きい順に最大数(1〜8)まで残す → 合計1へ振り直す → 精度(2〜4桁・8-bit の 1/255・16-bit の 1/65535)へ丸める(誤差は最大剰余法で配り、合計をちょうど1にする)。skinCluster の maxInfluences の固定、不要なインフルエンスの削除、処理の範囲(対象だけ・選んだメッシュ全部・シーンのバインド済みメッシュ全部)を選べる。Analyze は最大使用数・頂点ごとの数の分布・上限超え・合計のずれ・極小・段階のずれ・不要なインフルエンスを表示し、Select Problems は直す頂点を選ぶ。Limit Bones は skinCluster のインフルエンスの数を上限まで減らす(合計の小さいジョイントから親へ移して外す)。Analyze はウェイトの合計の小さいインフルエンスと、左右の対が無いインフルエンス(`L_` だけで `R_` が無い等)も表示する。Remove Matching は `*_end, *_helper` のような名前のパターンに合うジョイントを、ウェイトを親へ移してから外す。Copy Report で結果をクリップボードへコピー |
| Bind | Closest Joint(最も近いボーンへ100%の硬い初期ウェイト)、バインド(方法と最大数)、Bind Pose、Move Joints(押してからジョイントを動かし、もう一度押してバインド位置にする。メッシュの形は変わらない)、Remove Unused、Remove Selected Joints(選んだジョイントを影響しているすべての skinCluster から外し、ウェイトを最も近い親のインフルエンスへ移す。親子を一緒に選ぶと残る祖先へ集まる) |
| Skin Settings | skinCluster の設定(スキニング方法 Classic Linear/Dual Quaternion/Weight Blended・正規化の方法・最大数・最大数の維持)を読み、Apply で書く(既定は閉じる) |
| Transfer / Files | Pick Source で元のメッシュを覚え、Add Source Influences で元にあって対象に無いインフルエンスを足し、Copy from Source で選んだ頂点(またはメッシュ全体)へ最も近い頂点のウェイトを写す、Copy Skin to Meshes(最初に選んだメッシュから残りへ最近点でコピー)、頂点の位置を含む JSON への書き出しと、頂点の番号または最も近い位置(頂点数が違うメッシュにも使える)での読込み。頂点を選んでいればその頂点だけに読み込む。足りないインフルエンスをシーンのジョイントから足せる。mlib の `dumpWeights` の JSON も番号で読める |

- どの操作もロックしたインフルエンスの値は変えず、残りで合計を1にします。各ボタンの操作は1回の Undo です。
- 全部品と右クリックの全項目に、英語のツールチップで使い方を出します。パネルの右上の `?` で HTools の説明ページを開きます。
- 主な操作は runTimeCommand(カテゴリ `Custom Scripts.Skin Weight Kit`)として登録するので、Hotkey Editor でキーを割り当てられます。
  ほかに Loop・Ring・Hold・Fetch・Smooth/Sharpen のブラシも登録します。
  `SkinWeightKitValueMenu` はマウスの位置に値のメニュー(0〜1・Add/Subtract・Hammer・Smooth・Copy/Paste)を出し、
  Paint Skin Weights ツールを開かずに、頂点を選んだまま値を入れられます(パネルでアクティブにしたインフルエンスが対象)。

## テスト

```bat
"C:\Program Files\Autodesk\Maya2027\bin\mayapy.exe" maya\inhouse\SkinWeightKit\python\skinWeightKit\__tests__\run_tests.py
python maya\inhouse\SkinWeightKit\python\skinWeightKit\__tests__\run_gui.py --versions 2027
```

`run_tests.py` は新しいシーンへ切り替えるので、作業中の Maya GUI へは送らないでください。`run_gui.py` は使い捨ての Maya GUI を起動します。

## mlib との関係

処理(`core`)は mlib だけを使い、OpenMaya を直接使いません。ソフト選択(`Selection.getSoftSelection`)、
Grow/Shrink(`Vertices.grow`・`shrink`)、Loop/Ring(`Edges.getLoop`・`getRing`)、シェル・三角形・左右の頂点・
最も近い頂点(`Mesh.getShells` 等)、ロック、行での読み書き、ジョイントの一括削除、デフォーマーのウェイト
(`GeometryFilter.getDeformerWeights`)、skinCluster の設定は mlib 10.1.0 の API を使います。


## 今後の候補

位置・名前で対応させる読込み、詳しいウェイトの表、エッジのループ・リングの選択、ビューポートの中ボタンのメニュー。
