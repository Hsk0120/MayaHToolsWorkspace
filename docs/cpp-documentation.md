# 内製C++のコメント規約

heditを含む内製C++には日本語のDoxygen形式を使います。PythonのGoogle形式docstringと同様に、目的・引数・戻り値を説明します。外部submoduleへ一括適用しません。

```cpp
/**
 * @brief 指定行へカーソルを移動する。
 * @param line 1始まりの行番号。
 * @return 移動できた場合true。範囲外ならfalse。
 * @note 文書本文は変更しない。
 */
bool goToLine(int line);
```

- ファイルには`@file`と役割、クラスには責務を記載する。
- 公開・内部・特殊メソッドを含む全ての名前付き関数を説明する。ヘッダーで説明した関数は実装で重複させなくてよい。
- 引数は`@param`、非voidの戻り値は`@return`。失敗表現、変更する状態、所有者、単位も必要に応じて記載する。
- コンストラクターに`@return`を付けない。引数なしの関数に架空の`@param`を作らない。
- Qtの親子所有、`connect`、ラムダの捕捉、`deleteLater`、タイマー、Maya呼出は理由や実行順を補足する。
- ラムダは接続箇所のまとまりで説明する。単純な代入の逐語説明で本文を埋めない。
- 動作変更時はコメントも更新する。未検証の挙動を保証として書かない。

heditでは`editor.h`がMayaとの境界、`plugin.cpp`がMaya API、`editor.cpp`がQt編集画面、`explorer.*`がファイルツリーです。Qt部品は原則として親が所有し、`std::function`には呼び出す処理を渡します。補完も実行もMayaと同一プロセスです。

仕様: [Doxygenのコメント形式](https://www.doxygen.nl/manual/docblocks.html)。Doxygen自体はMaya実行やビルドの必須依存にしません。
