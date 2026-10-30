# Maya Code Editor

Maya用のPython／MELスクリプトエディタです。VS CodeのDark+を参考にした配色、タブ、行番号、補完候補、出力欄を備えています。mlibとは独立しています。

## 起動

0.2.2では上部ツールバーをMaya標準スクリプトエディタと同じアイコン中心の表示に変更しました。開く・保存、出力/入力/両方の消去、出力のみ/入力のみ/両方の表示、全体実行/選択実行、Explorerを配置しています。マウスを重ねると操作名とショートカットを表示します。入力の消去はCtrl+Zで戻せますが、出力の消去は戻せません。

各アイコンの操作はFile・Edit・History・View・Commandメニューからも選べます。Refresh completionはCommandメニューに移動しました。実行のCtrl+Enter／F5は従来どおりです。標準エディタの全機能を複製するものではなく、コードと出力のDark+配色も維持しています。

ワークスペースの起動バッチでMayaを起動すると、`maya/modules/MayaCodeEditor.mod`経由の`scripts/userSetup.py`が起動時に`Maya Code Editor`プラグインを自動ロードします。ロードした時点でWindowメニュー末尾に起動項目(緑のHアイコン)が追加され、前回開いていた場合は画面も自動で復元されます。`Maya Code Editor`本体のロジックは`.py`ファイルを持たず、`mayaCodeEditor.mll`自身が持っています。メニュー登録・ドッキング・開閉状態の保存と復元・出力の取得はC++で、補完と構文チェックだけをMaya同梱のPythonで行います(そのPythonも`src/python/`の`.py`をビルド時に`mayaCodeEditor.mll`へ同梱)。`scripts/userSetup.py`は`cmds.loadPlugin('mayaCodeEditor')`を呼ぶだけの最小ブートストラップで、Plug-in Managerでの明示ロードと同じ入口(`initializePlugin`)へ合流します。

Windowメニューの項目はMELの`mayaCodeEditor -show`を実行します。MEL・Pythonのどちらからでも開けます。

```text
mayaCodeEditor -show;
```

```python
import maya_code_editor
maya_code_editor.show()
```

Plug-in Managerで`Maya Code Editor`を明示ロード、または`Maya Code Editor`行で「Auto load」をチェックしてロードすることもできます(Maya標準の永続設定で、Maya Code Editor自身は変更しません)。起動済みのMayaには、`.mod` を追加した後の再起動が必要です。

プラグインの信頼確認が出た場合はMayaの画面で確認してください。Maya Code EditorはSecurity設定を変更しません。

基本補完はMayaと同じプロセス内で実行します。0.9.0の型解析とリファクタリングは専用の別プロセスを使います。旧版を起動済みの場合は、編集中のスクリプトとシーンを保存してMayaを再起動してください。C++プラグインはPythonの`reload()`だけでは更新されません。

初回はフローティング表示です。Mayaのドックタイトル部分をドラッグしてレイアウトへ配置できます。コードから下側へドッキングして開く場合は次のように指定します。

```python
maya_code_editor.show(floating=False)
```

`maya_code_editor.show(floating=True)`(MELは`mayaCodeEditor -show -floating true`)でフローティングに戻します。通常の`show()`は既存の配置を保持します。C++(`src/plugin/dock.cpp`)がMELの`workspaceControl`を作ってC++編集画面を直接入れ、復元用の`uiScript`(`mayaCodeEditor -restore`)も登録します。

### 未保存タブの自動復元

0.8.0では、全てのMayaが未保存の本文を独立した世代として保存します。本文は変更直後に同期保存し、入力停止・終了通知を待ちません。同じタブの並行編集は次回起動で両方を別タブとして復元します。復元したコードは自動実行しません。

保存先は`cmds.internalVar(userPrefDir=True)`の下の`MayaCodeEditor/tabs.json.recovery`です。圧縮した本文と確定世代を追記し、過去の内容を自動削除しません。旧`tabs.json`と`tabs/<id>.txt`は読込専用で移行・保護します。元の`.py`／`.mel`は上書きしません。Mayaバージョンごとに保存先が分かれます。

タブの×でDiscardを選ぶと次回の自動表示から外れますが、履歴は残ります。**File → Recover previous tabs…**からUTC日時付きの世代を選ぶと、現在のタブを消さず、新しい未保存タブとして追加できます。保存失敗はステータス欄へ常時表示し、自動再試行します。

ディスク故障・保存処理途中の停止・書込不能中の終了・IME未確定文字までは保証できません。復元履歴は編集量に応じて増えます。重要なコードは通常のファイル保存とバックアップを併用してください。旧版を起動中の場合は、編集中のコードを保存してMayaを再起動すると更新が反映されます。詳しい保存方式・復旧手順・検証は[自動保存と復元](docs/session.rst)を参照してください。

## 型解析・リファクタリング（0.9.0）

追加セットアップで、型に基づく補完・診断、スタブ、未保存タブ間の解析、参照検索、名前変更、自動import、意味色分け、型／引数ヒントを利用できます。変数／関数の抽出、別モジュールへの移動、import整理も追加しました。

解析は専用の別プロセスで行います。編集案は下見してから未保存タブへ反映し、元ファイルへ自動保存しません。MayaのPython環境は変更しません。導入手順・操作・範囲の制限は[型解析とリファクタリング](docs/language_services.rst)を参照してください。未導入時は従来の基本補完を利用できます。

## 操作

| 操作 | キー／場所 |
| --- | --- |
| 補完候補 | 入力時、または Ctrl+Space |
| 候補の確定 | Enter／Tab |
| 選択範囲を実行（選択なしなら全体） | Ctrl+Enter |
| タブ全体を実行 | F5 |
| 新規／開く／保存 | Ctrl+N／Ctrl+O／Ctrl+S |
| 名前の説明（ホバー） | 名前にマウスを重ねる／Ctrl+K → Ctrl+I |
| 検索 | Ctrl+F |
| 補完情報の再取得 | Refresh completion |
| 出力の消去 | 出力欄を右クリック → Clear output、またはツールバー |

0.8.1では、カーソル行より前に定義した現在の関数の引数・ローカル変数、if／for／with内の変数や分割代入も補完します。別関数のローカル変数は混ぜず、コードは実行しません。候補表示中の通常Enterは、入力済みの名前と完全一致する場合も確定だけを行い、次のEnterで改行します。Ctrl+Enter／テンキーEnterの実行操作は従来どおりです。

0.8.2では、ドット補完も本文で参照できる名前に限定します。例えば`import maya.cmds as cmds`を書いた場合は`cmds.`で候補が出ます。未importのモジュール名や、別関数の中でだけimportした名前は補完しません。`def`／`class`の新しい名前と`as`の別名を入力中も通常候補を出しません。`import`文の途中では未importのモジュールを探せます。組み込み関数・予約語、前方一致と省略入力による絞り込みは維持します。未import候補の自動追加は既定で行いません。0.9.0の型解析ではSuggest auto importsで有効にできます。

0.8.3では、f文字列の`{式}`を通常のコードとして色分けし、変数候補・引数ヒント・括弧と引用符の自動入力を利用できます。リテラル、`{{`、`!r`、書式指定の文字部分では自動候補を抑え、`{value:{width}}`のような入れ子の式は補完します。単一/二重/三重引用符に対応しますが、実行可能な構文は各Maya同梱Pythonのバージョンに従います。

関数呼出し中は`count=`のようなキーワード引数を優先表示します。指定済み・位置専用・位置引数で使用済みの名前は除外します。本文の通常関数、コンストラクター、インスタンスメソッド、明示した`staticmethod`/`classmethod`を区別します。`*args`/`**kwargs`で展開した内容や任意デコレーターの実行結果は推測しません。同一行でも`;`まで確定した変数とimportは以降の候補に利用できます。型推論は既存の静的解析の範囲で、言語サーバー全体と同等ではありません。


### 選択範囲の実行（Maya形式）

0.1.5ではコード欄が実行キーを直接受け取ります。更新前のプラグインを使用中ならMayaを再起動してください。

- コードをドラッグ、またはShift+矢印で選択し、Ctrl+Enterで選択した部分だけ実行します。Ctrl+Lで現在行を選択してから実行することもできます。
- 選択がない場合は現在タブ全体を実行します。カーソル行だけの実行ではありません。
- テンキーのEnter（Ctrl併用も可）でも同じ実行ができます。通常のEnterは改行です。
- 実行後もコードと選択範囲は保持します。F5／Run allは選択に関係なくタブ全体を実行します。
- 選択した文字列をそのままPythonとして実行します。関数・for文などは必要なブロック全体を選択してください。インデントの自動除去や不足した文の補完は行いません。

選択してCtrl+Enterで実行する操作は[AutodeskのScript Editor説明](https://help.autodesk.com/cloudhelp/2023/ENU/Maya-Scripting/files/GUID-7C861047-C7E0-4780-ACB5-752CD22AB02E.htm)を参考にしています。MELも実行できますが、標準Script Editorの全機能を再現するものではありません。

### VS Code系ショートカット（Windows）

0.1.4から対応しています。更新前のMaya Code Editorをロード済みの場合はMayaを再起動してください。Maya Code Editorにフォーカスがある間だけ有効です。編集操作はコード欄を対象にし、MayaシーンのUndoとは別のテキストUndoで戻せます。

| キー | 操作 |
| --- | --- |
| Ctrl+/ | 選択行／現在行のコメント切り替え（Pythonは#、MELは//） |
| Alt+↑ / ↓ | 選択行／現在行を移動 |
| Shift+Alt+↑ / ↓ | 選択行／現在行を複製 |
| Ctrl+Shift+K | 選択行／現在行を削除 |
| Ctrl+L | 現在行を選択。繰り返すと次の行まで拡張 |
| Tab / Shift+Tab | 選択行のインデント／解除（選択なしのTabは空白4文字） |
| Ctrl+] / Ctrl+[ | 現在行／選択行のインデント／解除 |
| Ctrl+C / Ctrl+X | 選択範囲をコピー／切り取り。選択なしなら現在行 |
| Ctrl+Z / Ctrl+Shift+Z | テキストUndo／Redo |
| Ctrl+F / Ctrl+H | 検索バー／置換バーを表示 |
| F3 / Shift+F3 | 次／前の一致箇所。末尾／先頭で折り返す |
| Escape（検索欄） | 検索バーを閉じてコードへ戻る |
| Ctrl+G | 操作中のコード欄・出力欄で指定行へ移動（行番号入力後Enter、Escで取消） |
| Ctrl+Shift+S | 名前を付けて保存 |
| Ctrl+W / Ctrl+F4 | 現在タブを閉じる（未保存なら確認） |
| Ctrl+Tab / Ctrl+Shift+Tab | 次／前のタブ |
| Ctrl+PgDown / Ctrl+PgUp | 次／前のタブ |
| Alt+Z | 折り返し表示の切り替え |

検索は現在タブ内を対象にします。バーの配置・大きさ・アイコン・動きはVS Codeの検索ウィジェットに合わせ、色はMaya Code Editorの配色、入力欄と件数の文字はエディターと同じフォント・大きさです（アイコンは`mayaCodeEditor.mll`内で描画し、画像ファイルは使いません）。検索欄へ1文字入力するごとに一致箇所と件数が更新され、Enterは不要です。入力を追加しても現在の一致を基準に絞り込みます。空欄にすると選択と件数表示を解除します。Enter/F3は次の一致、Shift+Enter/Shift+F3は前の一致へ移動します。入力欄の右上に重ねて表示し、Ctrl+Fで検索、Ctrl+Hまたは左端の`›`で置換欄を開きます(置換欄は検索欄の真下に同じ幅)。Escapeで閉じます。検索欄の中の`Aa`で大文字小文字の区別、`ab`(下に括弧)で単語単位、`.*`で正規表現を切り替えます（初期状態は全てオフ、オンは青い背景と枠）。三本線のボタンは選択範囲内で検索、置換欄の中の`AB`は大文字小文字を保つ置換です。検索欄の右に「1 of 4」の形で件数を表示し、一致なしは件数を赤く、不正な正規表現は検索欄の枠を赤くして理由を欄の下の吹き出しに出します。本文の中の全ての一致箇所には薄い背景を付けます。置換ボタンは現在の一致箇所、すべて置換ボタンは現在タブ全体(選択範囲内で検索がオンならその範囲)を対象にします。一括置換は1回のUndoで戻せます。

正規表現はQtのQRegularExpression方式です。正規表現モードの置換では`$1`〜`$99`をキャプチャー、`$&`を一致全体、`$$`をドル記号として扱います。通常モードは入力文字をそのまま使用します。名前付き参照や`\\1`記法は未対応です。不正な正規表現、長さ0の一致、10万件を超える一致は通知して処理を止め、置換しません。

### 表示倍率（0.1.10）

View → Zoom in / Zoom out / Reset zoom、またはCtrl+=（Ctrl++）／Ctrl+-／Ctrl+0でコード欄と出力欄の文字サイズを変更できます。コード欄は10〜28px（標準14px）、Outputは2px小さい8〜26px（標準12px）で、設定は次回起動に引き継ぎます。Maya標準のメニュー等のサイズは変更しません。

既存の実行操作を保つため、**Ctrl+Enterはスクリプト実行のまま**です。VS Codeの「下に行を挿入」とは異なります。F5もMaya Code Editorでは全体実行です。マルチカーソル（Ctrl+Dなど）、コード整形、画面の分割、コマンドパレット、VS Code全機能のキー互換は未対応です。定義へ移動（F12）・記号へ移動（Ctrl+Shift+O）・折りたたみなどは0.4.0で対応しました（docs/shortcuts.rst）。

キーの参考: [VS Code Windows公式ショートカット](https://code.visualstudio.com/shortcuts/keyboard-shortcuts-windows.pdf)。

0.1.2から、コードはMaya標準のPython実行経路で実行し、変数の名前空間も標準Script Editorと共有します。Maya Code Editorの実行結果はMaya共通の出力へ流れ、標準Script Editorにも表示されます。Maya Code Editor側はMaya標準reporterの表示文書と`MCommandMessage`の種別通知を購読し、他のエディタからの出力・警告・エラーも表示します。stdout/stderrの置き換えは行いません。シーン操作のUndo可否は実行したコマンドに従い、自動のUndoチャンクは追加しません。

0.2.3から、初回表示時にMayaが保持する履歴を最大512Ki文字取り込みます。Maya起動時の出力も、保持されていれば表示します。その後は新しい出力通知を購読し、初期履歴と重複させません。Mayaですでに消去された履歴や、別エディタ独自のログは復元できません。Clear outputはMaya Code Editorの表示だけを消去します。Maya Code Editor本体とスクリプト実行・補完はMayaと同じプロセスです。

Result／Warning／ErrorはMaya自身が整形した記号と改行を使用し、結果は緑、警告は黄、エラーは赤で表示します。Pythonの`print`にはコメント記号を追加しません。履歴の読み取りにはMaya標準の[cmdScrollFieldReporter](https://help.autodesk.com/cloudhelp/ENU/MayaCRE-Tech-Docs/CommandsPython/cmdScrollFieldReporter.html)を使用し、標準エディタの履歴・フィルター設定は変更しません。

補完候補の確定による本文変更では次の自動補完を予約しません。Enterで候補を確定した後、次のEnterで改行できます。

Maya 2024／2027のGUIで、標準Script Editorとの双方向出力、変数共有、日本語、警告・例外、出力が重複しないことを確認しています。CharcoalEditor2もMaya共通出力を使用する範囲では共有対象ですが、実物との連携テストは専用環境のプラグイン信頼確認で停止したため未確認です。信頼設定の自動変更は行いません。

出力欄を上、コードのタブを下に配置しています。中央の境界をドラッグして高さを調整できます。ファイルはUTF-8を使用します。通常のドックを閉じる操作では非表示になり、そのMayaセッション中はタブを保持します。

0.2.9から、Mayaメインスレッドのログ通知はタイマーを待たず最大約40fpsでOutputへ反映・再描画します。シーン読み込み中も通知に合わせて表示し、操作イベントを強制処理する`processEvents`は使用しません。最後の未描画分は25msタイマーで反映します。他スレッドからの出力はMaya自身のreporterがメインスレッドで文書へ反映するまで遅れる場合があります。Maya自身がまだ出力していない内容は表示できません。

## Outputの表示モード（0.2.7）

上段のアイコンバーでNormal（全種別）、Output only（実行コードのHistoryを除外）、Warnings + Errors、Errors onlyを切り替えます。保持中のログはモードを戻すと再表示します。Maya側のEcho Allや他エディタの設定は変更しません。初回履歴は警告・エラー・結果の接頭辞以外に種別情報がないため、過去の実行コードはOutput onlyでも表示される場合があります。

Output専用の見出しバーと保存・クリアボタンはありません。クリアは従来のアイコンバー、Historyメニュー、右クリックから操作でき、全モードの保持ログも消去します。保持上限は約100万文字、表示は最大5,000ブロックです。上限を超えて破棄した古いログは復元しません。表示モードの初期値はNormalです。

## Outputとスペルチェック（0.2.5）

Outputは標準12pxで、標準状態では折り返しません。横長の行は水平スクロールできます。Edit → Preferences → Wrap output linesで折り返しを切り替えます。起動履歴はMayaの表示用Qt文書から取得します。過去の通知区切りが改行に変換されているため、初回取り込みでは空行を省略し、空白だけの行を挟む断片（`optimization on`など）を接続します。この過去履歴では意図的な空行との区別や、区切り文字のない任意の分割出力の完全復元はできません。表示開始後のライブ出力にはこの圧縮を適用せず、分割printと意図的な空行を維持します。タイトルは文字化けを避けるASCII表記です。

Edit → Preferences → Spell check (English)で英語のスペル波線を切り替えます。標準はONです。Windows標準のen-US辞書を利用するため、外部Pythonライブラリ・辞書の同梱・オンライン送信は不要です。辞書が利用できない場合はステータスバーに表示します。

入力停止から450ms後に、アクティブなPython/MELタブの表示範囲（最大8,000文字）だけをチェックします。4〜40文字の英単語が対象で、camelCaseとsnake_caseを分割し、語単位で結果をキャッシュします。カーソル行の背景と青い波線を併用し、OFFにすると波線と保留中の検査を消します。Maya/Pythonの代表的な語は除外していますが、独自名には誤検出があり得ます。日本語の校正、修正候補、ユーザー辞書、cSpell設定ファイルの互換性は対象外です。文法エラーを調べるStatic analysisとは独立しています。

参考: [WindowsのスペルチェックAPI](https://learn.microsoft.com/en-us/windows/win32/api/spellcheck/nn-spellcheck-ispellchecker)。

## 外観（0.1.9）

メニュー・タブ・ツールバー・ステータスバーはMayaの標準Qtスタイルを継承します。出力上／コード下の配置を保ち、コード欄と出力欄だけをDark+配色・Consolas（コード14px、Output 12px）にしています。背景`#1e1e1e`、通常文字`#d4d4d4`、変数`#9cdcfe`、関数`#dcdcaa`、クラス`#4ec9b0`、文字列`#ce9178`、コメント`#6a9955`はmlibのSphinx `code-dark-plus.css`に合わせています。出力は通常文字色を基本とし、エラー行を赤、警告行を黄で区別します。

色の分類は簡易なPython構文強調のため、PygmentsやVS Codeの意味解析と完全に同じ色分けにはなりません。

### 出力の色（0.1.11）

0.1.12では出力欄をマウスやShift+矢印で選択し、Ctrl+Cでコピーできます。Ctrl+Aは出力欄の全選択、右クリックのCopyも使用できます。出力は読み取り専用で、貼り付けや文字の削除はできません。

0.2.1から出力欄の行番号はデフォルトで非表示です。Edit → Preferences → Show output line numbersで表示でき、設定は次回起動にも保持します。コード欄の行番号は常に表示します。行番号は桁数・文字サイズ・スクロールに追従し、コピーする本文には含まれません。非表示でもCtrl+Gの行移動は利用できます。出力をClearした場合や5,000行の上限で古い行が消えた場合は、残っている本文の先頭を1行目とします。

0.1.14では操作したいコード欄または出力欄をクリックし、Ctrl+Gで下部に行番号入力欄を開けます。1始まりの行番号を入力してEnterで移動、Escで取り消します。Maya 2024ではEsc後にフォーカスがビューポートへ戻る場合があるため、その場合はコード欄・出力欄をクリックして操作を続けてください。

新しいログが表示されると、スクロール位置にかかわらず必ず最下部へ移ります(選択範囲は保持します)。表示上限の5,000行を超えて削除された古いログや、Clear outputで消した文字列は保持対象外です。

0.2.10から、専用の非表示Maya reporterが整形した表示文書の追記だけを取得します。通常のPython/MELのprintはそのまま、情報通知は`// `、Pythonの警告・例外は`# Warning:`／`# Error:`など、標準Script Editorと同じ記号・改行になります。複数行の通知や空行にもMaya側の書式を適用し、独自の末尾` //`は追加しません。

Mayaの通知種別を保持しつつ、表示行の`# Error:` / `// Error:`、`# Warning:` / `// Warning:`、`# Result:` / `// Result:`も着色します。複数行の通知は見出しを着色し、続きの行は通常色です。着色だけでは通知種別を変えず、Errors only等の絞り込みは実際の種別を使います。

| 種別 | 色 |
| --- | --- |
| Warning見出し | 黄 `#dfe527` |
| Error見出し | 赤 `#f42828` |
| Result見出し | 緑 `#2ab422` |
| Info | 通常色（追加色をオンにすると水色 `#9cdcfe`） |
| History | 通常色（追加色をオンにするとグレー `#a0a0a0`） |
| Display・通常のprint | 明るいグレー `#d4d4d4` |

通常の`print("# Error: ...")`も赤くなりますが、エラー通知として再分類はしません。行中や字下げ後の接頭辞は対象外です。情報・履歴の追加色はPreferencesの **Color output info and command history** で切り替えます（初期オフ）。Maya標準エディターや他ツールの表示は変更しません。

Outputは枠なし・余白4px、選択色は明るい青と白文字です。Output専用文字サイズは8〜40px（標準12px）で、Ctrl+ホイール・右クリック・View > Output font sizeから変更とリセットができます。コード欄とは別に保存します。旧設定はコード欄-2pxを引き継ぎます。

## 補完の仕組み

- 補完は`mayaCodeEditor.mll`の中のC++で行います(`src/core/completion_engine.cpp`)。別プロセス・IPC・ワーカーの起動待ちはありません。
- 現在の`sys.path`とロード済みモジュールの公開名を使用します(この2つだけを同梱の`maya_code_editor.bridge`でPythonから受け取ります)。
- 編集中の本文と未ロードのソースの宣言は、C++の字句解析で読みます(`src/core/python_declarations.cpp`)。補完対象をimport・実行しません。5,000行の本文でも1回の補完は数ミリ秒です。
- ソース解析はキャッシュし、更新時刻・サイズが変わったら再解析します。ロード済みの`maya.cmds`などでは実在名を優先し、検索パスを走査しません。

以下は基本補完の説明です。0.9.0の追加型解析は別プロセスを使用します。基本補完だけなら追加のPythonライブラリは不要です。同一プロセスのメインスレッドで補完するため、遅いネットワークパス上の未ロードのモジュールを初めて読む間はMayaの操作も待機します。旧版の別ワーカー停止によるタイムアウト機能はありません。

`import maya.cmds as cmds`の別名、`from package import Class`、モジュールの公開名、ソース上のクラスの直接定義メソッド、トップレベルのローカル関数を補完します。ロード済みの`mlib.ls`など動的な公開名も対象です。関数の引数名は候補のツールチップで確認できます。

0.1.7から、次の補完要求時に対象モジュールの現在の公開名と`sys.path`を取得します。`mlib.reload()`後や実行後のimportもRefresh completionなしで追従します。読み込み済みモジュールは既知の`.py`ファイルだけを更新日時・サイズで確認し、関数やクラスの直接定義も候補へ反映します。`import xxx`/`from xxx`のトップレベルのパッケージ名は、`sys.path`の各フォルダーをC++のスレッド(PythonのGILを取らない)で走査して集めます(`src/core/module_scanner.cpp`)。走査は編集画面を開いた時点で始めるため、最初のCtrl+Spaceから未読込のパッケージも候補に出ます(初回の走査が終わっていなければ最大0.5秒待ちます)。以後はimport補完のたびに裏で走査し直し(開始は最短5秒間隔)、走査中は直前の結果で即時表示します。Maya APIと公開名の取得はメインスレッドで行います。

補完候補の更新と、Mayaで実行するライブラリの更新は別です。ソース保存直後に新しい候補が出ても、実行にはライブラリ自身のreloadが必要な場合があります。Maya Code Editorは対象を自動import・reloadしません。読み込み済みの公開名は実際に存在する間は残ります。解析中の構文エラーでは読み込み済みモジュールの最後の正常な静的候補を維持します。強制的に解析キャッシュを作り直す場合は **Refresh completion** を押してください。

0.2.5では自動補完を入力停止から250ms後に実行します。宣言部分の解析をキャッシュし、構文エラー時の再試行を最大4回、補完対象をカーソルまで20万文字に制限します。全ロード済みモジュールの属性を起動時に一括JSON化する処理も廃止しました。スペルチェックは引き続きC++です。

## 編集・補完の設定

**Edit → Preferences**で次の項目を切り替えられます。設定は復元ファイルと同じフォルダーの`preferences.json`へ保存し(変えた項目だけを書き換えます)、次回起動にも適用します。

| 項目 | 動作／初期値 |
| --- | --- |
| Completion while typing | 文字入力時の自動補完。オン |
| Completion after dot | ドット入力時の自動補完。オン |
| Include Python keywords / built-ins | キーワード／組み込み名を候補へ含める。オン |
| Static analysis (syntax / warnings) | 編集中タブの構文診断。オフ |
| Smart indentation | Enter時にインデントを引き継ぎ、末尾がコロンなら4空白追加。オン |
| Backspace to indentation stop | 行頭の空白を4文字の区切りまで削除。オン |
| Show spaces and tabs | 空白・タブを可視化。オフ |
| Trim trailing spaces on file save | 明示的なファイル保存時に行末空白を削除。オフ |
| Ensure final newline on file save | 明示的なファイル保存時に末尾改行を追加。オフ |

自動補完を両方オフにしてもCtrl+Spaceによる手動補完は使えます。保存時の整形はタブ復元用の自動保存には適用しません。元ファイル保存が成功した時だけコード欄にも反映し、1回のテキストUndoで整形前へ戻せます。インデント幅は現在4空白固定です。

### 静的解析（0.1.8）

Edit → Preferences → **Static analysis (syntax / warnings)**でオン／オフを切り替えます。初期状態はオフで、設定は次回起動にも保持します。補完のオン／オフとは独立しています。

オンの場合、現在のタブで入力が止まってから0.8秒後に、Maya同梱Pythonのコンパイラで構文を確認します。対象コードの実行・import・reloadや、外部の解析パッケージは使用しません。問題一覧はコード欄の下に表示し、クリックすると該当行へ移動します。編集やタブ切り替え時に古い診断を消し、再解析します。オフにすると待機中の解析と表示を取り消します。

構文エラー、インデントエラー、関数外のreturn、一部のSyntaxWarningが対象です。最初の構文エラーを修正すると次を確認できます。基本解析は限定的な未定義名も検出します。追加の型解析を導入すると型・引数・importの診断も利用できます。Maya APIの検証精度は型スタブに依存し、Pylintの全ルールは対象外です。診断内容は各MayaのPythonバージョンに従います。

Mayaと同じプロセスで同期解析するため、解析中は短時間UIが待機します。100万文字超、または2万行以上は解析を省略します。この上限は実行時間の保証ではありません。重い場合はオフにしてください。

## 現段階の制限

- PythonとMELを実行できます。MEL補完・MEL静的解析、デバッガー、VS Code拡張機能は未対応です。PythonのLSPは0.9.0の追加セットアップで利用できます。
- 追加型解析では戻り値・継承・ネストしたスコープも扱います。実行時に生成される型や任意の動的属性まで完全には解決しません。
- zip内ソース、未ロードのバイナリ拡張、`__getattr__`で生成される未知の属性は完全には補完できません。
- 補完は静的な名前の候補であり、型・構文の正しさを保証するものではありません。
- スクリプト実行自体はMayaのメインスレッドで行うため、長時間の実行中はMayaが待機します。
- WindowsのMaya 2022（Python 3）／2023／2024／2025／2026／2027向けにビルドします。各版の検証範囲は実行ログと`WORK_LOG.md`を参照してください。offscreenテストの合格は実機入力の確認とは区別します。

## 開発・テスト

リポジトリ直下から実行します。Maya devkitとVisual Studioの既存ビルド基盤を使用します。

```powershell
& 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' tools/build_maya_plugin.py maya/inhouse/MayaCodeEditor --versions 2022 2023 2024 2025 2026 2027
& 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' maya/inhouse/MayaCodeEditor/tests/run_tests.py 2022 2023 2024 2025 2026 2027
```

テストは補完ユニットテスト、Maya standaloneでの`.mod`／プラグイン／実在する補完候補の確認、同じC++ウィジェットによるoffscreen描画・補完挿入・実行ボタン確認に分かれています。ログ・画像は`.maya-output/mce-tests/`に保存します。offscreen検証とMaya GUI内での操作確認は別です。

GUI確認は次のコマンドで、既存のMayaとは別の空シーン・専用設定を使用して実施できます。

```powershell
& 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' maya/inhouse/MayaCodeEditor/tests/run_gui.py 2024
& 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' maya/inhouse/MayaCodeEditor/tests/run_gui.py 2027
& 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' maya/inhouse/MayaCodeEditor/tests/run_gui.py 2027 --suite editing_selection_smoke.py
& 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' maya/inhouse/MayaCodeEditor/tests/run_gui.py 2027 --suite search_navigation_smoke.py
& 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' maya/inhouse/MayaCodeEditor/tests/run_gui.py 2027 --suite search_navigation_smoke.py --manual-focus --timeout 240
& 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' maya/inhouse/MayaCodeEditor/tests/run_session.py 2024 2027
& 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' maya/inhouse/MayaCodeEditor/tests/run_startup.py 2024 2027
```

`editing_selection_smoke.py`は改行・引用符・字下げ・選択・単語操作とUndo／Redoを検査して画面を記録します。`search_navigation_smoke.py`は検索・置換と操作後のフォーカスを検査します。両方ともQtで合成した入力で、Windowsの実キー入力ではありません。検索テストでホストがフォーカスを移した場合は失敗として記録します。同じ専用画面でCtrl+F、検索語入力、Enter、Shift+Enter、置換欄でEnter、Escape、Undo／Redoを実際に操作し、本文とフォーカスを別途確認してください。

検索テストの`--manual-focus`は、開始前に専用画面の「Start search verification」を90秒以内にクリックするモードです。Windows上の前面化を実クリックで行ってから同じQt検査を開始し、入力種別を結果に記録します。無操作の合成入力テストで発生したフォーカス移動を、製品の実操作でも起きる不具合と混同しないための切り分けに使います。

テスト用モジュールディレクトリにはMaya Code Editorの`.mod`だけを用意します。ワークスペース全体の外部モジュールを読み込んでいた従来の起動タイムアウトは、この構成で解消しました。普段の起動バッチ・ユーザー設定・信頼設定は変更しません。外部ツールを全て有効にした構成の互換性検証とは別です。

GUI内で表示、上下レイアウト、ドッキング／フローティング／再表示、右クリックによる出力消去、コード全体の実行、標準Script Editorとの双方向の出力・変数共有、日本語・警告・例外の表示、実際の補完候補の表示、Enterによる確定、選択範囲だけの実行、閉じる／アンロードを確認します。ショートカットはキーイベントで行編集・Undo/Redo・検索置換・タブ操作・折り返しを確認します。行番号入力、フォルダー/ファイル選択（Qtダイアログ）も自動テストに含めます。OSネイティブのファイルダイアログは別途確認が必要です。結果・画面・候補一覧の画像を`.maya-output/Maya Code Editor-gui/<日時>/`に保存します。

`run_startup.py`は同じ専用Maya設定を引き継いで3回起動し、右ドック・Python/MEL本文の復元と、閉じた場合の非表示を検証します。あわせて、プラグインのロードだけでWindowメニューの項目とアイコンが追加されること、メニューのコマンド(`mayaCodeEditor -show`)で開けること、アンロードで項目が消えることも確認します。共通GUIランナーはuserSetupを無効化するため、`scripts/userSetup.py`と同じ`cmds.loadPlugin('mayaCodeEditor')`を起動後に明示実行します。通常環境でのuserSetup自動実行そのものはこのテストの対象外です。

過去の検証結果と変更内容はリポジトリの`WORK_LOG.md`を参照してください。

起動／テストの期限は各120秒、終了待ちは30秒です。`--timeout`と`--shutdown-timeout`で秒数を指定できます。タイムアウト時はテストが起動したプロセスだけを停止します。`result.json`はGUIテスト自体、`monitor.json`は起動／実行／終了の監視、`run-result.json`は両者をまとめた結果です。テスト成功後もMayaが終了しなかった場合は、GUI成功と終了タイムアウトの両方を記録し、終了コードは1になります。

表示される速度計測はキャッシュ済み名前検索だけの所要時間です。初回解析・UI描画・ネットワークドライブを含む操作全体の速度ではありません。


## 0.2.0の使い方

- File → New Python tab / New MEL tabで言語を選んで作成します。右下のPython／MELで現在タブの言語を変更できます。Ctrl+NはPythonタブ、Ctrl+Enterは選択部分（選択なしなら全体）、F5は全体を実行します。言語はタブの自動復元データにも保存します。
- 基本解析はアクティブなPythonタブが対象です。追加型解析では全Pythonタブの未保存本文を共有します。MELは解析しません。MELは`//`コメントと波括弧のインデントに対応しますが、色分けは簡易表示です。
- File → Open folderでExplorerのルートを置換、Add folderで複数フォルダーを追加します。保存済みファイルを開くと、その親フォルダーとOPEN EDITORSに表示します。ツリーのファイルをダブルクリックして開けます。Removeは表示ルートを外すだけでディスクから削除しません。
- View → Explorer、ツールバーのExplorer、Ctrl+Bでサイドバーを表示/非表示にします。フォルダー一覧と表示状態もタブとともに復元します。対象は.py/.melとフォルダー。展開時に直下だけを読み、シンボリックリンクは辿りません。
- タブが収まらない場合は左右のスクロールボタンを表示します。タブ上のホイールでも隣のタブへ移動します。Ctrl+Tab／Ctrl+Shift+Tabも使用できます。
- Ctrl+F/Ctrl+Hで検索/置換を開きます。VS Codeと同じ大きさ・アイコンの2段表示で、Aa・ab・.*・AB、前後移動(↑↓)、選択範囲内で検索、1件/全件置換を操作します。VS Code全機能の再現ではなく、現在タブ内の検索が対象です(履歴・複数ファイル検索・保存したフィルターは対象外)。

### Maya再起動時の画面復元

復元先はMaya Code EditorのworkspaceControlを明示的に使用し、内部の非表示ログウィンドウへ入らないようにしています。既存ドックを再表示する際は親ホストと本文の両方を表示します。

前回開いていた場合は、Mayaの保存ワークスペースに登録された`uiScript`(`mayaCodeEditor -restore`)から画面を再構築します。プラグインのロード後、次のイベントループでC++(`src/plugin/dock.cpp`)が前回の状態を確かめて復元するため、Plug-in Managerでの明示ロード・Mayaのプラグインautoloadのいずれでも同じ復元が行われます。ドックの入れ子・タブ位置はMaya標準のワークスペースに保持し、終了通知で現在の配置を保存します。ユーザーが閉じてから終了した場合は自動表示しません。

タブの並びと本文の履歴は`tabs.json.recovery`、開閉状態・フローティング状態・ワークスペース名は同じフォルダーの`ui.json`に保持します。終了中のUI破棄で「閉じた」扱いに書き換わることを防ぎます。元のMayaワークスペースが削除された場合は厳密な位置を復元できず、以前ドックしていた画面は下側に配置して警告します。Windowメニューまたは`maya_code_editor.show()`からも開けます。信頼設定を自動変更する機能はありません。

### Visual Studioプロジェクトだけを生成

```powershell
& 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' tools/build_maya_plugin.py maya/inhouse/MayaCodeEditor --versions 2022 2023 2024 2025 2026 2027 --generate-only
```

`.maya-output/plugin-build/Maya Code Editor/2024/Maya Code Editor.sln`または`2027/Maya Code Editor.sln`をVisual Studioで開きます。通常のビルドでも同じプロジェクトを生成します。`.maya-output/`はGit除外済みで、.sln/.vcxprojは登録しません。構成変更は生成されたプロジェクトではなくCMakeLists.txtへ反映します。

`maya/inhouse/MayaCodeEditor/generate_vs.bat 2027`でも生成できます（年の省略時は2027）。Visual StudioではRelease／x64でビルドします。ロード済み.mllを上書きしないよう、ビルド前に該当Mayaを終了してください。

CMakeを正本にしてIDEプロジェクトを生成する構成は一般的です。Visual Studio自体もこの生成・ビルドの分離に対応しています。[Microsoft公式説明](https://learn.microsoft.com/en-us/cpp/build/cmake-projects-in-visual-studio?view=msvc-180)。

C++の説明は[内製C++コメント規約](../../../docs/cpp-documentation.md)に従う日本語Doxygen形式です。ヘッダーの引数・戻り値、実装の所有権やイベント順序を合わせて読めます。PythonはGoogle形式docstringを維持します。

## 名称

フォルダは`maya/inhouse/MayaCodeEditor`、プラグインとコマンドは`mayaCodeEditor`、Pythonのパッケージは`maya_code_editor`、C++の名前空間は`mce`です。
起動は`import maya_code_editor; maya_code_editor.show()`、またはMELの`mayaCodeEditor -show`です(`mayaCodeEditor`プラグインが
一度でもロードされていれば、`.py`ファイルなしで`sys.modules['maya_code_editor']`から解決されます)。

## プラグインロードだけで復元・メニュー登録が完結する仕組み

`maya/maya_core.bat`は`maya/modules`を`MAYA_MODULE_PATH`へ追加しています。
`MayaCodeEditor.mod`はバージョン別の`MAYA_PLUG_IN_PATH`に加え、`scripts/userSetup.py`を
見つけるための`PYTHONPATH +:= scripts`を設定します。`userSetup.py`はGUI初期化後に
`cmds.loadPlugin('mayaCodeEditor')`を1回呼ぶだけの最小ブートストラップで、復元・メニュー登録の
ロジックは一切含みません。

`initializePlugin`(`src/plugin/plugin.cpp`)は、Windowメニューの登録を`installWindowMenu()`
(`src/plugin/window_menu.cpp`。MEL、`MGlobal::executeCommand`経由)で行います。メニューの緑のHアイコンもSVGを
`window_menu.cpp`がメモリ上で描いてメニュー項目へ直接付けるため(ファイルは書き出しません)、`icons/`フォルダーは不要です。続けて
次のイベントループで`src/plugin/dock.cpp`が前回画面の復元を行います。ドッキングはMELの`workspaceControl`と
`MQtUtil::addWidgetToMayaLayout`で、`MayaQWidgetDockableMixin`は使いません。そのため**`userSetup.py`経由の
自動ロード・Plug-in Managerでの明示ロード・Mayaのプラグインautoloadのどれでも、プラグインの
ロードだけでメニュー登録と前回画面の復元が完了します。**
Pythonでしか分からない情報の窓口(`maya_code_editor.bridge`)・構文チェック(`maya_code_editor.analysis`)と互換用の窓口(`maya_code_editor.show()`/
`maya_code_editor.restore()`)は`src/python/`の`.py`をビルド時に`mayaCodeEditor.mll`へ同梱し、`sys.meta_path`の先頭へ登録したimportフックから
配ります(通常の`.py`と同じくimport時に読み込まれ、mayapyでも使えます)。
初回はエディタ画面を開かず、前回開いていた場合だけ画面・タブを復元します。
バッチ/standaloneでは画面を開きません(`userSetup.py`は`cmds.about(batch=True)`を検知して何もしません)。
Mayaの永続autoload設定はMaya Code Editor自身が変更しません。

GUI回帰テストは隔離環境で`cmds.loadPlugin('mayaCodeEditor')`を明示実行し、メニュー登録・ドッキング・復元を
確認します(C++の画面は`tests/gui_host.py`経由で参照)。ユーザー環境の全外部ツールを含む起動バッチ実行とは区別しています。

構文警告はMaya同梱Pythonの仕様に従います。例えば2022のPython 3.7では、定数への`is`比較で新しいPythonと同じ警告は出ません。

## 起動済み画面の開き直し

`maya_code_editor.show()`やWindowメニューを繰り返し実行すると、既存の本文を一度閉じてから同じ画面を開き直します。
未保存タブ・編集状態・ドッキング位置は保持します。Pythonのモジュールをreloadした場合も
Maya内の既存ホストを回収するため、新しい画面を重ねて作りません。
この操作はプラグインのアンロードやコードの再読み込みではありません。
