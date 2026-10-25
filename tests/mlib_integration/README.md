# mlibと他パッケージの連携テスト

mlib本体の単体・結合テストとは分けて管理します。このフォルダはワークスペース側に残し、
mlibを別リポジトリへ分離する際の必須ファイルには含めません。

| フォルダ | 内容 |
| --- | --- |
| `cases/` | mlrig・HTools・mlib拡張・cymelとの連携 |
| `gui/` | 外部プラグインの専用GUI確認 |
| `manual/` | 起動済みGUIへの送信、外部投稿などの手動スクリプト |

このワークスペースのルートから実行します。`cases`は必要なパッケージがある環境で実行し、
依存がない場合のImportError等も失敗として記録します。テストを黙って除外しません。

```powershell
python maya/inhouse/mlib/__tests__/runMaya.py --versions 2027 --suite-file tests/mlib_integration/run.py --output .maya-output/mlib-integration
```

本体の環境分離・ログ集計を使い、`cases/`だけを実行します。
`manual/`のスクリプトは自動実行しません。Slackへの実投稿は送信の明示指示がある場合だけ行います。
旧HTools APIを使う手動疎通スクリプトも含むため、個別スクリプトは内容と依存を確認してから実行してください。

本体のテスト方法は`maya/inhouse/mlib/__tests__/README.md`を参照してください。
