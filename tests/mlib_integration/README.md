# mlibと他パッケージの連携テスト

mlib本体の単体・結合テストとは分けて管理します。このフォルダはワークスペース側に残し、
mlibを別リポジトリへ分離する際の必須ファイルには含めません。

| フォルダ | 内容 |
| --- | --- |
| `cases/` | mlrig・HTools・mlib拡張・cymelとの連携 |
| `gui/` | 外部プラグインの専用GUI確認 |

このワークスペースのルートから実行します。`cases`は必要なパッケージがある環境で実行し、
依存がない場合のImportError等も失敗として記録します。テストを黙って除外しません。

```powershell
py -3 maya/inhouse/mlib/__tests__/runMaya.py --versions 2027 --suite-file tests/mlib_integration/run.py --output .maya-output/mlib-integration
```

本体の環境分離・ログ集計を使い、`cases/`だけを実行します。
`cases/`のファイル名は本体の`integration/`と同じく`test_<観点>_<話題>.py`にします(規則は本体のREADME)。
起動済みGUIへ表示確認を送る`tools/send_mlib_visual_gui.py`と、Slackへ実際に投稿する`tools/post_slack_test_message.py`は
自動実行しません。Slackへの実投稿は送信の明示指示がある場合だけ行います。

本体のテスト方法は`maya/inhouse/mlib/__tests__/README.md`を参照してください。
