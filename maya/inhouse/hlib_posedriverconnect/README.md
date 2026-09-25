# hlib PoseDriverConnect拡張

PoseDriverConnect v2のPythonモデルAPIを使い、`UERBFSolverNode`と
`UEPoseBlenderNode`をhlibノードとして扱うサンプルです。
外部ソース・バイナリをコピーしたり、独自Mayaプラグインを実装したりしません。

## 導入

- hlib、PoseDriverConnectのPythonパッケージ`epic_pose_wrangler`をPython探索パスへ追加します。
- 外部APIが使用する`six`（requirements.txt参照）も必要です。未導入の場合は拡張状態が`error`になり、hlib標準機能は継続します。自動インストールはしません。
- `maya/modules/hlib_posedriverconnect.mod`はこの拡張の`scripts/`を探索パスへ追加します。
- `import hlib`で`hlib_*`拡張が検出されます。`userSetup.py`は不要です。
- Maya上でノードを作成・評価するには、そのMayaバージョンに対応する製品のプラグインが必要です。拡張自身はロードしません。
- 導入後の再検出は`hlib.reload()`で行います。取得済みオブジェクトは取得し直してください。

このリポジトリで実ノードを検証できるWindowsバイナリは2022・2024版です。
対応バイナリがないバージョンではPythonクラスの登録と実ノードの動作確認を区別してください。

## 利用

```python
import hlib

print(hlib.extensions.status())

# 対応プラグインとシーン内のソルバーがある場合
for solver in hlib.ls(type="UERBFSolverNode"):
    print(solver.drivers())       # list[hlib.nodes.Node]
    print(solver.num_poses())
    print(solver.radius())
    solver.set_radius(45.0)      # Undo可能

for blender in hlib.ls(type="UEPoseBlenderNode"):
    print(blender.driven_transform())  # NodeまたはNone
    print(blender.envelope())
```

`native_api()`はPoseDriverConnectのモデルラッパーを返します。
その戻り値を直接操作した場合のUndo・副作用は外部APIの仕様に従います。
サンプルの編集メソッドは`set_radius()`のみです。全外部APIを自動公開しません。

専用属性データ型のないサンプルなので`plugs/`は設けていません。
数値・行列などはhlib標準のPlugを使い、グローバルな属性型登録を上書きしません。

## GUIと.modの起動確認

リポジトリ直下から実行します。

```powershell
& 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' tools/run_hlib_extension_gui.py --versions 2024 --timeout 240
```

専用prefsのMaya GUIを新規起動し、実際の`maya/modules`を読み込みます。
外部APIや拡張のPythonパスをテスト内で追加せず、moduleInfoと拡張状態を確認します。
対応バイナリがある環境では`.mod`の配置先から対象バイナリを明示ロードし、専用クラス取得、
半径編集、Undo/Redo、リロードを検証します。既存の作業用Mayaには接続しません。
対応バイナリがない場合の実ノード試験はスキップとして記録します。

結果JSONとGUI画像は`.maya-output/extension-gui/`へ保存します。
GUI起動・テスト・終了を監視し、タイムアウト時は所有プロセスだけを停止します。
テストの成功と終了タイムアウトは別々に記録します。
`worker-entered.json`は起動コマンドへの到達、`gui-readiness.json`はGUI表示待ちの状態、
`started.json`はスイート開始を示します。起動前失敗をテスト成功として扱いません。

MetaHumanにも同名の`MayaUERBFPlugin`があるため、名前だけのロードでは別製品の
バイナリが選ばれる場合があります。テストではロード元のパスも検証します。
