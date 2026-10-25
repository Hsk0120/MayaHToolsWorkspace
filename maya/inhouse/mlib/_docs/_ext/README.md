# mlib固有の文書生成処理

本文を編集する場合は、[上のREADME](../README.md)にあるRST・docstringを直してください。
このフォルダは、標準のAutoAPI表示に足している処理をまとめたものです。

| ファイル | 担当 |
| --- | --- |
| `mlibDocs.py` | Sphinx・AutoAPIと、下の2つの処理をつなぐ |
| `_mermaidClasses.py` | Pythonの継承関係を読み、クラスページ用のMermaidソースを作る |
| `_constructorSignatures.py` | 単数Nodeの派生クラスに、継承した生成時引数を表示する |

## 呼ばれる順序

1. `source/conf.py`がこのフォルダをPythonの検索先へ追加し、`mlibDocs`をSphinx拡張として指定する。
2. Sphinxが`mlibDocs.setup()`を呼び、配置名の反映・constructor掲載の補正を登録する。
3. AutoAPIがmlibのPythonソースを解析する。
4. `source/conf.py`の`autoapi_prepare_jinja_env`に指定した`prepare_autoapi()`が、テンプレート用の関数を登録する。
5. `source/_templates/autoapi/python/class.rst`が継承図・生成時引数・docstringをページに展開する。
6. `source/_includes`の概要図は`whymlib.rst`へ差し込む。配置名の反映は通常の本文とincludeの両方へ行う。
7. HTMLを開くと、`source/_static/js/mermaid-init.js`がMermaidで図を描く。

Mayaやmlibはimportしません。基底クラスを調べるときもPythonソースを静的に解析します。
解析したAPIやシーンの状態を書き換える処理は追加しません。

## 変更箇所を探す

- 図の継承関係・リンク先: `_mermaidClasses.py`。
- 図の配色・描画後の寸法: `source/_static/js/mermaid-init.js`と`source/_static/css/mermaid.css`。
- Node派生クラスの生成時引数: `_constructorSignatures.py`。既存検証は`tools/test_mlib_constructor_signatures.py`。
- クラスページ内の掲載順: `source/_templates/autoapi/python/class.rst`。
- 対象パッケージ・AutoAPIオプション・Mermaidの版: `source/conf.py`。

`mlibDocs.py`の`autoapi-packaged/`という名前は、独自テンプレートからAutoAPI標準テンプレートを参照するためにあります。
`module.rst`同士が同名なので、この区別を外すと自分自身を読み込んでしまいます。
再公開された`mlib.cmds`の重複警告だけを除く処理も、このファイルにあります。
それ以外の警告は通常どおり検査対象です。

内部を変更したら、ビルドしてページの見出し・引数・継承図・リンクを確認してください。
