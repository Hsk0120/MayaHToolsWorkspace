# Anim Bar

タイムスライダーの上にドックする、アニメーション作業用のツールバーです。
処理は mlib だけで書き(`animBar.core`、Qt を使わない)、画面は PySide(`animBar.ui`)です。
アイコンは画像ファイルを使わず、`animBar/ui/icons.py` で描いています。

## 起動

- `maya/modules/AnimBar.mod` が有効なら、Maya GUI の起動後に自動でバーを表示します(前回閉じていれば表示しません)。
- HTools > animation > animBar、またはスクリプトの `import animBar; animBar.toggle()` で表示・非表示を切り替えます。
- 主な操作は runTimeCommand(カテゴリ `Custom Scripts.Anim Bar`)として登録するので、Hotkey Editor でキーを割り当てられます。

## 機能

| 区切り | ボタン | 内容 |
| --- | --- | --- |
| Tween | 前のキー・スライダー・後ろのキー・プリセット | 前後のキーの間の値でキーを打つ。スライダーの端を越えると行き過ぎ |
| Keys | モード・スライダー・左右の時刻・細かい足し引き | 選んだキーを、前後のキー・既定値・記録した時刻・反対側のコントロールへ近づける、直線から押し出す、イーズ、揺らす |
| Tangents | auto〜plateau・flow・bounce | 接線型の設定。flow は前後のキーを結ぶ向き、bounce は山・谷を flat |
| Time | キーを前後へ・間を空ける/詰める・キーをそろえる・前後のキーへ・範囲・プレイブラスト | キーの時間の操作と再生範囲の保存・切替、プレイブラスト |
| Pose | リセット・ミラー・入替え・全体へ反映・コピー・貼付け | ポーズの左右反転、変更を全キーへ反映、アニメーションのコピー(別キャラクター・現在時刻へずらす・反転) |
| Space | 位置合わせ・スペース切替・仮のピボット・仮のコンストレイント | ワールドの位置を保つ操作。範囲を指定するとフレームごとにキーを打つ |
| View | モーショントレイル・細かい移動・タンブル・退避 | 表示の補助と、クラッシュに備えたアニメーションの退避 |
| Sets | 選択セットのボタン・作成 | 色付きの選択セット(クリックで選択、Shift で追加、Ctrl で除外)。書出し・読込み |

左右の対応は名前(`L_`/`R_`・`_L`/`_R`・`Left`/`Right` 等)で探します。反転するアトリビュートの既定は、左右のコントロールが `translateX`、中心のコントロールが `translateX`・`rotateY`・`rotateZ` で、ミラーの右クリックで変えられます。
ノードに `animBarMirrorInvert`(カンマ区切りの文字列)を足すと、そのノードで反転するアトリビュートを変えられます。

## aTools との違い

挙動は aTools を参考にしていますが、コードは流用していません。次は未対応です。

- アニメーションレイヤー・pairBlend を介したカーブ(animCurve が直接つながったアトリビュートだけを扱う)
- キー変形の scaleFrom 系のモードと、修飾キーでのモード切替
- 接線の First Frame / Last Frame 等の範囲指定と、タイムラインのハイライト範囲の利用
- 選んだキーの範囲でのアニメーションのミラー(ポーズのミラーのみ)、反対側の選択
- transformAll の変更前の値を覚えるトグル方式(自動キーで打った後は差が0になる)
- プレイブラストの音声・オーバースキャン等の設定、退避の起動時の確認

## テスト

```bat
"C:\Program Files\Autodesk\Maya2027\bin\mayapy.exe" maya\inhouse\AnimBar\python\animBar\__tests__\run_tests.py
python maya\inhouse\AnimBar\python\animBar\__tests__\run_gui.py --versions 2027
```

`run_tests.py` は処理のテスト(mayapy)、`run_gui.py` は使い捨ての Maya GUI でバーの表示・ドックの位置・操作を確かめ、
画像を `__tests__/_output/`(Git 対象外)へ残します。どちらも作業中の Maya GUI では実行しません。
