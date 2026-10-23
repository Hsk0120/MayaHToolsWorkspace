# mlrigの実装ルール

mlrigはmlibを基本ライブラリとして使用する。Pythonコードの書き方とdocstringは、mlibの既存実装および [mlib API設計](mlib-api-design.md) に合わせる。

## 実装の境界

- ノード生成・参照は `mlib.createNode()` / `mlib.getNode()`、アトリビュートと接続は `Node` / `Plug` の公開APIを優先する。共通基底の正式入口は `mlib.core.object.Object`、拡張管理は `mlib.core.extensions`。実行フォルダ名だけで公開/非公開を判断せず、通常は各クラスの公開APIへ委譲する。クラスに属さない小さな汎用関数は `mlib.util`、横断的なデコレーターは `mlib.decorator` を使う。
- scriptJobの登録・生存確認・解除、汎用的なアトリビュート操作など、リグ以外でも使える処理はmlibへ実装する。リグの状態判断、FK/IKの姿勢合わせ、レイヤー依存関係はmlrigに置く。
- Mayaへの問い合わせやシーン更新はメソッドにする。プロパティは保持している参照や識別子などに使用する。Undo可能な更新を既定にする。
- mlrig本体・UI・startup・examplesでは既存mlib APIを優先する。`mlib.cmds`の7入口以外の標準操作は `maya.cmds` を直接使用し、必要な戻り値だけをmlib参照へ変換する。汎用の生成ラッパーは再追加しない。テストは独立した検証のため直接cmdsを使用してよい。
- 既定のリグとデモはMaya標準ノードだけで構築する。Bifrost/C++は明示選択する任意バックエンドとし、mlrig起動時に自動ロードしない。
- Bifrost固有操作はmlib_bifrost、独自C++リグノードはmlrigの責務とする。mlibへ独自プラグインを追加しない。

## 書式とdocstring

- インデントは4スペース。mlibオブジェクトの公開メソッド・コマンドは `lowerCamelCase`、クラスは `PascalCase`、定数は `UPPER_SNAKE_CASE` とする。mlrigの既存APIと内部変数は周辺実装に合わせ、命名の一括変更を機能整理へ混ぜない。
- セミコロンで複数処理を連結せず、1行1処理とする。演算子・カンマの前後の空白と複数行の引数整形はmlibの周辺コードに合わせる。
- モジュール・クラス・名前付き関数に日本語の説明を記載する。最初の文で役割や結果を説明し、必要な補足を段落に分ける。
- 関数の引数は `Args:`、戻り値は `Returns:`、利用者が扱う例外は `Raises:` に記載する。各セクションの前に空行を入れ、型・意味・既定値を説明する。存在しない引数や例外の形式的な説明は増やさない。
- 座標を扱うAPIにはローカル／ワールド空間、角度・距離の単位を記載する。シーン変更、Undo、所有する生成物、GUI限定などの制約も明記する。
- 実装していない機能をdocstringで保証しない。変更時は説明・実装・テストの整合を確認する。

```python
def set_layer_enabled(self, layer, enabled):
    """任意レイヤーの使用設定を変更し、計算経路へ反映する。

    Args:
        layer (str): 対象レイヤーの識別子。
        enabled (bool): Trueの場合に使用する。

    Raises:
        ValueError: 対応していないレイヤーを指定した場合。
    """
```

## 検証

共通APIはmlib側で検証し、mlrig側ではFK/IK・LOD・保存読込・Undo/Redoの統合動作を検証する。scriptJobはGUIのアイドル処理で動くため、standaloneのテストだけで動作確認済みとしない。テストには隔離したシーン／Mayaプロセスを使い、ユーザーが編集中のシーンを破棄しない。


## 共通処理の配置

- 所有DGは`mlib.nodes.Container`の`create`・`createNode`・`addMembers`・`getMembers`を使う。
  レイヤー固有のノード名、所有グラフの選択と有効状態判断はmlrigで決める。
  所属だけの解除は`removeMembers`、メンバーを残す箱の解除は`removeContainer`を使う。
  公開名の操作は`publishName`・`bindAttribute`・`publishAndBind`・`getPublishedAttrs`を使う。
  箱自身の入出力アトリビュートを介する接続の移送は利用側が担当する。
- 保存用message配列は`ArrayPlug.getSourceNodes()`と`appendMessage()`を使う。
  前者は接続のある論理インデックスとノードの辞書、後者は既存最大番号の次へ追記する。
- 操作シェイプは`mlrig.setups.ControlShape`、単位境界は`mlib.common.units`を使う。
  Plugと数学型の距離はcm、角度はrad、時間は秒。UI単位のビルダー入力は境界で変換する。
  空間指定は`mlib.maths.MSpace`の定数を使う。
  型名が必要な場合は`Plug.getDataType()`を使用する（`Plug.getType()`はPythonクラス）。
- バインドと最近傍ウェイト転送は`SkinCluster.bind`・`copyWeightsTo`を使う。
  どの骨をLODへ含めるか、どのメッシュを表示するかはmlrigの責務とする。
- 単位なし標準DG演算は`mlib.common.scalarGraph.ScalarGraph`、Soft IKは`mlrig.setups.SoftIK`。
  コンテナを使わない場合は`ScalarGraph(create_node=...)`へNodeを返す生成関数を渡し、
  生成物を`ArrayPlug.appendMessage`等で記録する。一時コンテナを作る必要はない。
  Bifrostの演算構築は`mlib_bifrost.common.MathBuilder`、Soft IKは`mlrig.setups.bifrostSoftIK.SoftIK`へ置く。
- 共通APIへ依存方向を逆転させない。mlib/mlib_bifrostからmlrigをimportしない。
  移動時は使用側を新しいAPIへ更新し、旧import用アダプターは残さない。
- 基礎コマンドは`getNode/getPlug/createNode/ls/delete/duplicate/select`を使う。
  その他はMaya標準cmdsを直接呼び、Node/Plugが必要な境界だけ明示変換する。
  標準コマンドの引数へは必要に応じて`getFullName()`を渡し、shape/transform/履歴/effectorを区別する。

- mlrigからOpenMaya/OpenMayaUIを直接importしない。数学型は `mlib.maths` の
  Matrix/Vector/EulerRotate等、位置変換は `Matrix.transformPoint`、回転分解は
  `Matrix.quaternion`・`Matrix.euler` を使う。位置と方向の変換を混同しない。
  Qt親ウィンドウの取得・変換は利用側UIパッケージの責務とする。mlibはQtをimportせず、標準UIの名前・Mayaの通知APIを扱う。

- 標準UI名とEditor起動には利用側で`maya.mel`/`maya.cmds`を使う。
  メインウィンドウ名は`$gMainWindow`、標準Editorは`NodeEditorWindow`/`GraphEditor`へ委譲する。
  バッチ判定を行い、mlibへ汎用UIラッパーを再追加しない。
- アトリビュート内の通常JSON文字列はPython標準の`json.dumps/loads`を使う。
  同じ引数・文字列形式を維持し、独自の外枠や型タグを追加しない。
- Pythonの遅延呼出しは`mlib.common.Deferred.call(callback, *args, **kwargs)`を使う。
  シーンの選択は`mlib.common.Selection`、作業環境・ユーザー設定は利用側のMaya標準APIで扱う。
  汎用設定ストア・型付き保存フレームワークは再追加しない。

## リグセットアップの境界

Maya標準の概念・操作はmlibへ、リグの構成・追従・補正・コントロール設定は `mlrig.setups` へ置く。標準ノードだけで構成していてもリグの組み方を決める処理はmlrigの責務。Spline IKソルバーの作成は `maya.cmds.ikHandle` と戻り値のNode変換、CVコントロール接続・両端Twist・停止経路を組み合わせる構築は `mlrig.setups.SplineIK` とする。

`DrivenKey` は `mlib.common`、純粋なカーブ近似・減衰ばねは `mlib.common`。mlibとmlib_bifrostにはmlrigへの依存を作らず、セットアップのテスト・文書もmlrigに置く。

通知は `mlib.logger.warning/error/info`、通常のPython出力は `logger.print` に集約する。`mlib.warning` / `mlib.cmds.warning` は使用しない。

基礎7入口以外の標準操作は `maya.cmds` を直接使用する。削除した同名mlibコマンドを再追加しない。名前の戻り値をmlibで扱う場合は使用側でNode/Plugへ変換し、connections=TrueはMayaの平坦なペア列として扱う。


## 所有する参照への委譲

- Nodeを保持している場合は `node.getPlug("translateX").get()` を使い、名前を組み立ててgetPlugで再解決しない。Plugの距離はcmのため、取得後のUI単位からの再変換は不要。
- 入力だけを解除する場合は `destination.disconnectInput()` を使う。出力接続を維持し、未接続なら何もしない。親の複合接続は親Plugに対して解除する。
- 許可する接続元、リグの所有範囲、レイヤーの有効判定はmlrigで決める。検証や切断のためだけにMPlugへ降りず、既存の公開Plug APIを使用する。


## コントローラ形状の差し替え

`ControlShape.replaceCurves(target, points, knots, degree=1, name="ctrlCurve")` は
既存Transformを維持して直下のNURBSカーブを差し替え、Transformを返す。
点列はMayaの現在の距離単位で指定する。既存のTRSとカーブ以外のシェイプを保持し、
一連の変更は1回のUndoで戻せる。旧カーブのアトリビュートや接続は移送しない。
プリセットの寸法・カテゴリ・UIでの選択判断はHTools側に置き、作成処理を共用する。
