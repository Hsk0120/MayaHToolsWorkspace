# MayaCommandPorts

HToolsから独立したMaya commandPort初期化モジュールです。
依存はMaya標準の`maya.cmds`と`maya.utils`のみです。

`maya/modules/MayaCommandPorts.mod`がMayaCommandPorts直下をPython検索パスに追加し、
Mayaが`userSetup.py`を起動時に実行します。
GUI起動時に遅延実行で`:7001` (MEL)、`:7002` (Python)を開きます。
バッチでは実行せず、既存ポートは開き直しません。失敗はwarningに出力します。
HToolsのメニュー、初期化フラグ、トレースログには依存しません。

対応バージョン登録は既存HTools.modと同じ2022/2024/2025/2026/2027です。
maya_core.batは既にmodulesをMAYA_MODULE_PATHに追加するため変更不要です。
新規登録はMayaを再起動すると反映されます。

手動で再試行する場合:

```python
import maya_command_ports
maya_command_ports.initialize()
```

自動起動を無効にするにはMaya終了後にMayaCommandPorts.modをmodules外へ移動します。
実行中のポートを自動的に閉じることはありません。
7001/7002は既存commandPort専用で、JSON形式のvscode2mayaブリッジとは別プロトコルです。
