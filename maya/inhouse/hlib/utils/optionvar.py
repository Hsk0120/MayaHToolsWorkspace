"""cmds.optionVar のラッパー。ツール固有設定をシーンをまたいで永続化する。"""

import maya.cmds as cmds

#: None/True/False を optionVar の文字列値として区別して保存するためのトークン。
#: 実際のツール設定でまず衝突しない値にしている(NUL文字は MEL 文字列が
#: 途中で切れる原因になるため使わない)。
_NONE_TOKEN = "<<<hlibOptionVarNone>>>"
_TRUE_TOKEN = "<<<hlibOptionVarTrue>>>"
_FALSE_TOKEN = "<<<hlibOptionVarFalse>>>"


class OptionVar:
    """接頭辞で区切った cmds.optionVar を dict のように扱うラッパー。

    None/bool/int/float/str、および要素の型が揃った int/float/str の
    シーケンス(空シーケンスを含む)を値として保存できる。デフォルト値と
    型・値ともに一致する値は実際には保存せず、``optionVar`` の肥大化を防ぐ。
    """

    def __init__(self, prefix="", defaults=None):
        """接頭辞とデフォルト値を設定する。

        Args:
            prefix (str): 管理するキーに付与する接頭辞。既定は空文字(接頭辞なし)。
            defaults (dict | None): キーごとのデフォルト値。

        Returns:
            None: 値を返さない。
        """
        self._prefix = prefix
        self._defaults = dict(defaults) if defaults else {}

    def __repr__(self):
        """デバッグ表現を返す。

        Returns:
            str: クラス名と接頭辞を含む文字列。
        """
        return f"OptionVar(prefix={self._prefix!r})"

    def prefix(self):
        """str: 保持している接頭辞。"""
        return self._prefix

    def __contains__(self, key):
        """デフォルト値、または実際の保存値としてキーが存在するか判定する。"""
        return key in self._defaults or bool(cmds.optionVar(exists=self._prefix + key))

    def __len__(self):
        """int: keys() の件数。"""
        return len(self.keys())

    def __iter__(self):
        """Iterator[str]: keys() を順に返す。"""
        return iter(self.keys())

    def __getitem__(self, key):
        """保存値、無ければデフォルト値を返す。

        Raises:
            KeyError: 保存値・デフォルト値のいずれも無い場合。
        """
        full_key = self._prefix + key
        if cmds.optionVar(exists=full_key):
            return self._decode(cmds.optionVar(query=full_key))
        try:
            return self._defaults[key]
        except KeyError:
            raise KeyError(key) from None

    def __setitem__(self, key, value):
        """値を保存する。デフォルト値と型・値が一致する場合は実体を保存せず削除する。

        Raises:
            TypeError: 非対応の型、または要素の型が混在するシーケンスの場合。
        """
        full_key = self._prefix + key
        if key in self._defaults:
            default = self._defaults[key]
            if type(default) is type(value) and default == value:
                cmds.optionVar(remove=full_key)
                return
        self._store(full_key, value)

    def __delitem__(self, key):
        """保存値を削除する。デフォルト値には影響しない。

        Raises:
            KeyError: 保存値・デフォルト値のいずれも無い場合。
        """
        full_key = self._prefix + key
        existed = bool(cmds.optionVar(exists=full_key))
        if existed:
            cmds.optionVar(remove=full_key)
        elif key not in self._defaults:
            raise KeyError(key)

    def get(self, key, default=None):
        """保存値、無ければデフォルト値、どちらも無ければ default を返す。"""
        try:
            return self[key]
        except KeyError:
            return default

    def pop(self, key, *args):
        """値を取得して保存値を削除する。デフォルト値には影響しない。

        Args:
            key (str): 対象キー。
            *args: 見つからない場合の既定値。0 個か 1 個。

        Returns:
            object: 削除前の値。

        Raises:
            KeyError: 保存値・デフォルト値のいずれも無く、既定値も未指定の場合。
        """
        try:
            value = self[key]
        except KeyError:
            if args:
                return args[0]
            raise
        full_key = self._prefix + key
        if cmds.optionVar(exists=full_key):
            cmds.optionVar(remove=full_key)
        return value

    def keys(self):
        """list[str]: 実際の保存値とデフォルト値を合わせたキー一覧(重複なし)。"""
        stored = self._stored_keys()
        stored_set = set(stored)
        return stored + [key for key in self._defaults if key not in stored_set]

    def values(self):
        """list: keys() に対応する値一覧。"""
        return [self[key] for key in self.keys()]

    def items(self):
        """list[tuple[str, object]]: keys() に対応するキーと値のペア一覧。"""
        return [(key, self[key]) for key in self.keys()]

    def clear(self):
        """接頭辞配下の実際の保存値を全て削除する。デフォルト値は保持する。"""
        for key in self._stored_keys():
            cmds.optionVar(remove=self._prefix + key)

    def set_default(self, key, value):
        """デフォルト値を設定する。現在の保存値がその値と一致すれば実体を削除する。"""
        self._defaults[key] = value
        full_key = self._prefix + key
        if cmds.optionVar(exists=full_key) and self._decode(cmds.optionVar(query=full_key)) == value:
            cmds.optionVar(remove=full_key)

    def set_defaults(self, defaults):
        """辞書でデフォルト値をまとめて設定する。"""
        for key, value in defaults.items():
            self.set_default(key, value)

    def _stored_keys(self):
        """list[str]: 接頭辞配下に実際に保存されているキー一覧(接頭辞を除いた名前)。"""
        prefix = self._prefix
        start = len(prefix)
        return [key[start:] for key in (cmds.optionVar(list=True) or []) if key.startswith(prefix)]

    @staticmethod
    def _decode(value):
        """cmds.optionVar から取得した生値を Python 値へ復元する。"""
        if value == _NONE_TOKEN:
            return None
        if value == _TRUE_TOKEN:
            return True
        if value == _FALSE_TOKEN:
            return False
        return value

    @classmethod
    def _store(cls, full_key, value):
        """値の型に応じて cmds.optionVar へ保存する。

        Raises:
            TypeError: 非対応の型の場合。
        """
        if value is None:
            cmds.optionVar(stringValue=(full_key, _NONE_TOKEN))
        elif value is True:
            cmds.optionVar(stringValue=(full_key, _TRUE_TOKEN))
        elif value is False:
            cmds.optionVar(stringValue=(full_key, _FALSE_TOKEN))
        elif isinstance(value, str):
            cmds.optionVar(stringValue=(full_key, value))
        elif isinstance(value, float):
            cmds.optionVar(floatValue=(full_key, value))
        elif isinstance(value, int):
            cmds.optionVar(intValue=(full_key, value))
        elif isinstance(value, (list, tuple)):
            cls._store_sequence(full_key, value)
        else:
            raise TypeError(f"Unsupported optionVar value type: {type(value)!r}")

    @staticmethod
    def _store_sequence(full_key, values):
        """要素の型が揃った int/float/str のシーケンスを保存する。

        既存値は事前に削除してから積み直す。空シーケンスは、要素0件の配列として
        保存する(cmds.optionVar が単一値と空配列を区別できるようにするため)。

        Raises:
            TypeError: 要素が bool、非対応型、または型が混在する場合。
        """
        if cmds.optionVar(exists=full_key):
            cmds.optionVar(remove=full_key)
        if not values:
            cmds.optionVar(stringValueAppend=(full_key, ""))
            cmds.optionVar(clearArray=full_key)
            return
        first = values[0]
        if isinstance(first, bool):
            raise TypeError("Sequences of bool are not supported by optionVar")
        if isinstance(first, str):
            append_flag, cast = "stringValueAppend", str
        elif isinstance(first, float):
            append_flag, cast = "floatValueAppend", float
        elif isinstance(first, int):
            append_flag, cast = "intValueAppend", int
        else:
            raise TypeError(f"Unsupported optionVar sequence element type: {type(first)!r}")
        expected_type = type(first)
        for item in values:
            if isinstance(item, bool) or type(item) is not expected_type:
                raise TypeError("Mixed-type sequences are not supported by optionVar")
            cmds.optionVar(**{append_flag: (full_key, cast(item))})
