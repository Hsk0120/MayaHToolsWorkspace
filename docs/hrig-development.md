# hrigの実装ルール

hrigはhlibを基本ライブラリとして使用する。Pythonコードの書き方とdocstringは、hlibの既存実装および [hlib API設計](hlib-api-design.md) に合わせる。

## 実装の境界

- ノード生成・参照は `hlib.createNode()` / `hlib.getNode()`、属性と接続は `Node` / `Plug` の公開APIを優先する。hlibの `_core` など内部実装へ直接依存しない。
- scriptJobの登録・生存確認・解除、汎用的な属性操作など、リグ以外でも使える処理はhlibへ実装する。リグの状態判断、FK/IKの姿勢合わせ、レイヤー依存関係はhrigに置く。
- Mayaへの問い合わせやシーン更新はメソッドにする。プロパティは保持している参照や識別子などに使用する。Undo可能な更新を既定にする。
- hrig本体・UI・startup・examplesでは `maya.cmds` を直接使用しない。既存hlib APIを優先し、不足する操作は `hlib.cmds` に既存コマンドと同じ規則で追加し、ノード・属性はhlib参照として返す。新しい操作はhlib側へ追加して検証する。テストは独立した検証のため直接cmdsを使用してよい。
- 既定のリグとデモはMaya標準ノードだけで構築する。Bifrost/C++は明示選択する任意バックエンドとし、hrig起動時に自動ロードしない。
- Bifrost固有操作はhlib_bifrost、独自C++リグノードはhrigの責務とする。hlibへ独自プラグインを追加しない。

## 書式とdocstring

- インデントは4スペース。関数・メソッド・変数は `snake_case`、クラスは `PascalCase`、定数は `UPPER_SNAKE_CASE` とする。既存のMaya互換コマンド名は変更しない。
- セミコロンで複数処理を連結せず、1行1処理とする。演算子・カンマの前後の空白と複数行の引数整形はhlibの周辺コードに合わせる。
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

共通APIはhlib側で検証し、hrig側ではFK/IK・LOD・保存読込・Undo/Redoの統合動作を検証する。scriptJobはGUIのアイドル処理で動くため、standaloneのテストだけで動作確認済みとしない。テストには隔離したシーン／Mayaプロセスを使い、ユーザーが編集中のシーンを破棄しない。


## 共通処理の配置

- 所有DGは`hlib.nodes.Container`の`create`・`createNode`・`add`・`members`を使う。
  レイヤー固有のノード名、所有グラフの選択と有効状態判断はhrigで決める。
- 保存用message配列は`ArrayPlug.sourceNodes()`と`appendMessage()`を使う。
  前者は接続のある論理インデックスとノードの辞書、後者は既存最大番号の次へ追記する。
- 操作シェイプは`hrig.setups.ControlShape`、単位境界は`hlib.utils.units`を使う。
  Plugと数学型の距離はcm、角度はrad、時間は秒。UI単位のビルダー入力は境界で変換する。
  空間指定は`hlib.maths.MSpace`の定数を使う。
  型名が必要な場合は`Plug.dataType()`を使用する（`Plug.type()`はPythonクラス）。
- バインドと最近傍ウェイト転送は`SkinCluster.bind`・`copyWeightsTo`を使う。
  どの骨をLODへ含めるか、どのメッシュを表示するかはhrigの責務とする。
- 単位なし標準DG演算は`hlib.utils.scalarGraph.ScalarGraph`、Soft IKは`hrig.setups.SoftIK`。
  Bifrostの演算構築は`hlib_bifrost.utils.MathBuilder`、Soft IKは`hrig.setups.bifrostSoftIK.SoftIK`へ置く。
- 共通APIへ依存方向を逆転させない。hlib/hlib_bifrostからhrigをimportしない。
  移動時は使用側を新しいAPIへ更新し、旧import用アダプターは残さない。
- コマンド入口は `hlib.cmds`（および同一関数の `hlib` 再公開）へ置く。
  短縮フラグ正規化、入力参照の解決、Undo規則を既存コマンドに合わせる。
  ノードはNode、属性はPlug、UIはUiElementを返す。数値やboolの照会は値として返す。
  汎用の生cmds転送クラスは追加しない。リグの保存済み名前形式が必要な境界だけ
  `.name()` / `.fullName()` で明示変換する。

- hrigからOpenMaya/OpenMayaUIを直接importしない。数学型は `hlib.maths` の
  Matrix/Vector/EulerRotation等、位置変換は `Matrix.transformPoint`、回転分解は
  `Matrix.quaternion`・`Matrix.euler` を使う。位置と方向の変換を混同しない。
  MayaのQt親ウィンドウは `hlib.ui.MainWindow.widget()` で取得する。

- `maya.mel` もhrigから直接使用しない。メインウィンドウ名は
  `MainWindow.name()`、標準エディター起動は `NodeEditor.show()` / `GraphEditor.show()`
  を使用する。必要なMEL操作はhlibに責務を持つメソッドとして追加する。

- 標準 `json` をhrigで直接importしない。既存リグ属性の通常JSONは
  `hlib.json.JsonText.dumps/loads` を使用し、外枠・型タグを追加しない。
  hlib型・Snapshot保存用の既存 `hlib.json.dumps/loads` と用途を区別する。

- `maya.utils` の直接importも行わない。Pythonの遅延呼出しは
  `hlib.executeDeferred(callback, *args, **kwargs)` を使う。文字列コードは受け付けない。
- 作業環境・単位・選択は `hlib.environment.Workspace` / `Preferences` / `Selection` に配置する。
  実装はscene/ui/environment/eventsの用途別パッケージ配下の原則1クラス1ファイル（単数・対応する複数クラスは同居）。旧import用ファイルは残さず、使用側を新しい配置へ更新する。

## リグセットアップの境界

Maya標準の概念・操作はhlibへ、リグの構成・追従・補正・コントロール設定は `hrig.setups` へ置く。標準ノードだけで構成していてもリグの組み方を決める処理はhrigの責務。Spline IKソルバーの作成は `hlib.createIkHandle`、CVコントロール接続・両端Twist・停止経路を組み合わせる構築は `hrig.setups.SplineIK` とする。

`DrivenKey` は `hlib.scene`、純粋なカーブ近似・減衰ばねは `hlib.utils`。hlibとhlib_bifrostにはhrigへの依存を作らず、セットアップのテスト・文書もhrigに置く。

通知は `hlib.utils.logger.warning/error/info`、通常のPython出力は `logger.print` に集約する。`hlib.warning` / `hlib.cmds.warning` は使用しない。

指定された標準操作（about/currentTime/cutKey/deleteUI/keyframe/listConnections/listHistory/listRelatives/menu/menuItem/objExists/parent/playbackOptions/setKeyframe）は `maya.cmds` を直接使用する。削除した同名hlibコマンドを再追加しない。名前の戻り値をhlibで扱う場合は使用側でNode/Plugへ変換し、connections=TrueはMayaの平坦なペア列として扱う。
