型解析とリファクタリング（0.9.0）
================================================

basedpyright 1.40.2とRope 1.15.0を、MayaのGUIとは別の所有プロセスで利用します。
Pylance本体やVS Code拡張をMayaへ組み込む機能ではありません。
基本補完は追加セットアップなしで使えます。

セットアップ
------------

Node.js 20以降とPython 3.10以降を用意し、ワークスペースのルートで一度実行します。
このPythonはリファクタリング用プロセスにも使います。Maya 2022のPythonへ依存を追加する必要はありません。

.. code-block:: powershell

   & 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' maya/inhouse/MayaCodeEditor/tools/setup_language_server.py --node 'C:/path/to/node.exe'

専用キャッシュ ``%LOCALAPPDATA%/MayaCodeEditor/language-server`` に配置します。
Maya本体のsite-packagesは変更しません。セットアップ時だけネット接続が必要で、解析はローカル標準入出力通信です。
basedpyright配布物は固定版SHA-512を照合します。各依存のLICENSE/dist-info/licensesを保持します。
``server.json`` が起動設定です。``MCE_LANGUAGE_SERVER_CONFIG`` で別の設定を指定できます。
セットアップ後は **Command → Refresh completion** を実行します。
C++プラグインの更新時はMayaを再起動してください。

解析対象
--------

* Pythonの全文、カーソル位置、全タブの未保存本文を共有します。復元待ちタブも読み込みます。
* 標準型、関数戻り値、代入、self、コンテナ要素、Union/None/isinstance、overload、TypeVar/Protocolを解析します。
* ``.pyi``、``typings``、MayaのPython検索パスとプロジェクトの ``pyrightconfig.json`` / ``pyproject.toml`` を利用します。
* 起動時のルートは作業フォルダーから設定ファイル/リポジトリを探します。``MCE_PROJECT_ROOT`` でも明示できます。
* **File → Open folder / Add folder** で解析対象を追加します。最後のルートを新規仮想文書とリファクタリングに使います。
* 編集中ファイルの親フォルダーを最大200箇所監視します。深い階層や外部スタブの変更後はRefresh completionを使ってください。

要求は非同期で期限は30秒です。本文変更後の古い応答、別タブ/別入力欄へ移動した後の補完は反映しません。
サーバー不在/終了時や静的候補が空の場合は既存のMaya公開名の補完へ戻ります。
ユーザーのソースを補完のためにimport・実行しません。実行時に生成される属性や不正確なスタブは解決できない場合があります。

操作と設定
----------

* **F12 / Alt+F12**: 定義へ移動/下見。
* **Shift+F12**: 参照先一覧から移動。
* **F2**: シンボルの名前変更。全対象の変更前後を下見してApply。
* **Ctrl+.**: 該当位置のテキスト修正案。外部コマンドの実行だけの提案は適用しません。
* **Edit → Refactor → Extract variable/function**: 選択した式/処理を変数/関数へ抽出。
* **Move global symbol to module**: グローバル関数/クラス/変数を同一ルートの既存Pythonモジュールへ移動し、参照を更新。
* **Move global symbol to new module**: 同一ルート内の新しいPythonモジュールへ移動。新規タブは未保存で開きます。
* **Rename module and update imports**: Pythonモジュール名を変更し、ルート内のimportを更新。Apply時にディスク上のファイル名が変わります。パッケージ改名は対象外です。
* **Undo / Redo last refactoring**: 最後に適用した変更セットの本文とモジュール改名をまとめて戻す／再適用します。
* **Organize imports / remove unused**: import整理と未使用import除去。副作用目的のimportは下見で確認してください。

Preferencesの **Suggest auto imports** は既定OFFです。ON時は候補確定とimport挿入を1回のUndoで戻せます。
**Type-aware colors** は既定ONです。 **Type and argument hints** は既定OFFで、ヒントの対象位置に表示用の間隔を設けて描画します。
ヒントはコピー/保存される本文やUndo履歴に混入しません。行頭、タブ直後、UTF-16サロゲート直後のヒントは表示を省略します。
**Static analysis** は既定OFFです。ONにすると型・引数・importのエラー/警告をProblemsと波線へ表示します。
診断ルールはプロジェクト設定とスタブの精度に依存します。MELの型解析は対象外です。

Literal引数やTypedDictキーは、型解析が候補を返すと文字列内でも補完できます。
表示名の引用符を検索から除き、確定にはサーバーの置換範囲を使うため引用符を重複挿入しません。
通常は公開名を内部名より先に並べます。 ``_`` から入力すれば内部名も通常どおり検索できます。
同じ一致度の候補はサーバーの ``sortText`` 順位を使います。

番号付きLSPスニペットの既定値・選択肢の先頭値を展開し、Tab／Shift+Tabで入力箇所を移動できます。
Escape、Undo／Redo、入力範囲外の編集でスニペット操作を終了します。
変換式、変数、入れ子、同一番号のミラー参照は未対応で、該当候補は本文を変えず通知します。

変更の適用と制限
----------------

本文の変更案は下見後に未保存タブへ反映します。必要なタブを保存してください。
モジュール改名だけはApply時にディスクへ反映され、下見にも変更前後のパスを表示します。
既存の移動先を上書きしません。下見中や抽出計算中に対象が変化したら中止します。
通常のUndoは各タブ単位です。変更セット全体にはRefactorメニューのUndo／Redoを使用してください。
その後に本文を編集、タブを閉じる、別名保存した場合は一括復元を拒否します。
新規モジュールを保存した場合や改名先のディスク内容が変わった場合も、ファイルを消したり上書きしたりせず拒否します。
新規モジュールの一括Undoでは空の未保存タブが残ります。変更セットの記録は現在のエディター内で最後の1件のみです。
新規モジュールは保存するまで他ファイルからのimport解析で未解決と表示されることがあります。

抽出/移動/import整理は一時コピー上で計算します。 ``.ropeproject/config.py`` はコピー/実行せず、動的解析も無効です。
範囲は指定ルート内のPython、上限は5000ファイル・合計32Mi文字・1ファイル2MiB、期限は30秒です。
大規模プロジェクトでは小さいルートを指定してください。範囲外の依存先や名前を文字列で指定する動的参照は更新できません。
解析は型/構文の正しさを保証するものではありません。変更後はプロジェクトのテストも行ってください。

検証方法
--------

``tests/language_smoke.py`` は専用Maya GUIで補完、Enter確定、スタブ、診断、未保存タブ、リネーム下見/Undo、抽出を確認します。
``tests/test_refactor_worker.py`` は元データ保持、Unicode位置、抽出/移動/import整理を確認します。
``tests/ui_smoke.cpp`` はUTF-16範囲、同一位置のimport挿入、重複拒否とUndoを確認します。
専用の模擬サーバーで、要求取消・逆順応答・破損フレーム・再起動・破棄後のコールバック抑止も検査します。
Qtイベントの操作とOS入力の実機確認は検証報告で区別します。
