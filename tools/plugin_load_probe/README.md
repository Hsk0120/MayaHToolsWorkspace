# pluginLoadProbe

`.mll` のロードが Windows のセキュリティ機能(組織の管理ポリシー)に止められたとき、原因を切り分けるためのデバッグ用の最小プラグインです。

ロード・アンロード時に Script Editor へ1行出すだけで、他には何もしません。Qt・COM・Python・ファイルの読み書き・ネットワーク・別プロセスの起動は使わず、OpenMaya/Foundation 以外はリンクしていません。署名もしていません。

**セキュリティ機能を迂回するためのものではありません。** このプラグインも止められるなら、正しく止められているということです。許可されていない場所を探して置き場所を試し続けることはせず、結果を持って社内の管理者・プラグイン担当に相談してください。

## ビルド

```bat
python tools/build_maya_plugin.py tools/plugin_load_probe --versions 2026
```

`tools/plugin_load_probe/release/plug-ins/windows/<Mayaの年>/pluginLoadProbe.mll` ができます。Maya 2022〜2027 のビルド済みの `.mll` もこのフォルダーにコミットしてあるので、Visual Studio が無いPCでもビルドせずに使えます。ビルドし直すとコミット済みのファイルが書き換わるので、コミットする意図が無いときは `git checkout -- tools/plugin_load_probe/release/` で戻してください。`maya/modules/` には登録していないので、起動時に自動でロードされることはありません。

## 使い方

1. 止められた `hedit.mll` と**同じフォルダー**に `pluginLoadProbe.mll` をコピーします。
2. Maya の Script Editor(Python)でロードします。

   ```python
   from maya import cmds
   cmds.loadPlugin(r"<コピーしたフォルダー>\pluginLoadProbe.mll")
   ```

   成功すると `pluginLoadProbe loaded: <フォルダー>/pluginLoadProbe` と表示されます。
3. 終わったら `cmds.unloadPlugin("pluginLoadProbe")` でアンロードします。

## 結果の見方

| 結果 | 考えられる原因 |
| --- | --- |
| hedit と同じく止められる | プラグインの中身ではなく、**置き場所**(ドキュメントなど、ユーザーが書き込める場所の制限)か、**署名がない・実績のないファイル**であること |
| これはロードでき、hedit だけ止められる | hedit の中身(ファイルの評判やウイルス対策ソフトの判定など)が原因 |

どちらの場合も、止められた時刻のイベントログ(イベントビューアー → アプリケーションとサービス ログ → Microsoft → Windows)で、どの仕組みが止めたかを確認できます。

| ログ | イベントID | 止めた仕組み |
| --- | --- | --- |
| AppLocker → EXE and DLL | 8004 | AppLocker(置き場所や発行元のルール) |
| CodeIntegrity → Operational | 3077 | App Control for Business |
| Windows Defender → Operational | 1121 | 攻撃面の縮小ルール(ASR) |

管理者に相談するときは、このイベントの内容(ルール名・ID・ファイルのパス)を伝えると話が早く進みます。
