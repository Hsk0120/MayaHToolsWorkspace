"""通常のJSON文字列の変換。"""

import json as _json


class JsonText:
    """hlib形式の外枠や型タグを付けないJSON変換を提供する。

    標準jsonと同じオプション・既定値・例外を維持する。
    Nodeや数学型の保存には既存のhlib.json.dumps/loadsを使用する。
    """

    @staticmethod
    def dumps(data, **kwargs):
        """通常のJSON文字列へ変換する。

        Args:
            data (object): 標準jsonが扱える値。
            **kwargs: indent、ensure_ascii、allow_nan等の標準jsonオプション。

        Returns:
            str: 形式情報を追加しないJSON文字列。

        Raises:
            TypeError: 未対応の型やオプションの場合。
            ValueError: 循環参照、または指定オプションが値を拒否した場合。
        """
        return _json.dumps(data, **kwargs)

    @staticmethod
    def loads(text, **kwargs):
        """通常のJSON文字列を復元する。シーンへの適用は行わない。

        Args:
            text (str | bytes | bytearray): 通常のJSONデータ。
            **kwargs: object_pairs_hook等の標準jsonオプション。

        Returns:
            object: 辞書・リスト等の復元値。hlib型タグの解釈は行わない。

        Raises:
            ValueError: JSONの構文が不正な場合（JSONDecodeErrorを含む）。
            TypeError: 入力型やオプションが不正な場合。
        """
        return _json.loads(text, **kwargs)
