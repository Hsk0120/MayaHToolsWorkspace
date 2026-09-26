"""ツール設定を optionVar へ JSON 文字列として保存するストア。

optionVar はシーンを開き直しても消えず、GUI の Maya を終了するときなどに
``userPrefs.mel`` へ書き出されて次回起動時にも残る(バッチモードでは書き出されない)。
ただし optionVar 自体が保持できるのは文字列・整数・小数とその配列だけで、
``None`` や真偽値、入れ子のデータはそのままでは表せない。

:class:`~hlib.utils.optionvar.OptionVar` は「1 キー = 1 つの文字列型 optionVar」とし、
値を JSON テキストへ変換して格納する。読み出し時は JSON を解釈し直すため、
JSON で表せる値であれば型を保ったまま往復できる。optionVar 名は
``<接頭辞>.<キー>`` の形にして、ツールごとに名前が衝突しないよう分ける。

optionVar の値は ``userPrefs.mel`` へ書き出すときにエスケープされるが、名前は
エスケープされずにそのまま MEL の文字列リテラルへ埋め込まれる。名前に ``"`` や
``\\`` が混ざると ``userPrefs.mel`` が構文エラーになり、次回起動時に他の設定まで
読み込まれなくなるおそれがある。そのため接頭辞とキーに使える文字は、ASCII の
英数字と ``_`` だけに制限している。
"""

import json
import math
import re

import maya.cmds as cmds

# 接頭辞とキーをつなぐ文字。キー側には含められない(接頭辞の直下だけを列挙するため)。
_SEPARATOR = "."

# キー、および接頭辞を区切り文字で分けた各部分に使える文字列。
# userPrefs.mel の文字列リテラルへそのまま書けるよう、ASCII の英数字と "_" に限る
# (\w は ASCII 以外の文字にも一致するため使わない)。
_NAME_PART = re.compile(r"[A-Za-z0-9_]+")

# 「値が見つからなかった」ことを None と区別して伝えるための目印。
_MISSING = object()


class OptionVar:
    """接頭辞でまとめた optionVar 群を、JSON 値を持つ辞書のように読み書きする。

    キー ``key`` の値は optionVar ``"<prefix>.<key>"`` に JSON テキストとして保存する。
    値の取得は「保存済みの値」→「コンストラクタで渡したデフォルト値」の順に探し、
    どちらも無いキーは存在しないものとして扱う。

    保存できる値
        JSON で表せる値に限る。``None``・``bool``・``int``・``float``・``str`` と、
        それらを要素に持つ ``list``/``dict``。``float`` は有限値のみで、NaN と
        無限大は受け付けない。``dict`` のキーは ``str`` だけを受け付ける。
        入れ子が深すぎて ``json`` モジュールで変換できない値も受け付けない。
        ``tuple`` は JSON の配列として保存されるため、読み出すと ``list`` になる。
        ASCII 以外の文字は ``\\uXXXX`` 形式へエスケープして保存し、optionVar や
        ``userPrefs.mel`` 側の文字コードの影響を受けないようにする。

    デフォルト値の扱い
        デフォルト値と同じ値を保存した場合も、そのまま optionVar に書き込む。
        デフォルト値へ戻すには :meth:`reset` で保存済みの値を削除する。接頭辞の
        全キーをまとめて戻す場合は :meth:`reset_all` を使う。デフォルト値は
        コンストラクタでのみ指定でき、取り出すたびに新しいオブジェクトとして返すため、
        戻り値を書き換えてもデフォルト値には影響しない。

    JSON として読めない optionVar
        文字列以外の型の optionVar や、JSON として解釈できない文字列は、推測して
        変換せず「保存されていない」ものとして扱う。NaN・無限大の表記や、
        ``1e400`` のように ``float`` の範囲を超える数値を含む文字列、入れ子が
        深すぎて解釈できない文字列もこれに当たる。
        取得時はデフォルト値へフォールバックし、:meth:`stored_keys` には含めない。
        :meth:`set` で上書きでき、:meth:`reset`/:meth:`reset_all` で削除できる。

        一方、JSON として解釈できる文字列は、このクラス以外の手段で書き込まれた
        ものでも JSON として読む。例えば ``cmds.optionVar(stringValue=(name, "123"))``
        で書かれた値は文字列 ``"123"`` ではなく整数 ``123`` として、``"true"`` は
        ``True``、``"null"`` は ``None`` として返る。

    名前に使える文字
        接頭辞の各部分とキーは、ASCII の英数字と ``_`` だけで構成する
        (理由はモジュールの説明を参照)。この規則に合わない名前の optionVar は、
        接頭辞の直下にあっても一覧・削除の対象にしない。

    optionVar の変更は Undo の対象にならない。

    Examples:
        >>> settings = OptionVar("myTool", defaults={"size": 1.0, "axes": ["x"]})
        >>> settings.full_name("size")
        'myTool.size'
        >>> settings["size"]
        1.0
        >>> settings["size"] = 2.5
        >>> settings.is_stored("size")
        True
        >>> settings.reset("size")
        True
        >>> settings["size"]
        1.0
    """

    def __init__(self, prefix, defaults=None):
        """接頭辞とデフォルト値を指定してストアを作る。Maya の状態は変更しない。

        Args:
            prefix (str): optionVar 名の先頭に付ける名前。ASCII の英数字と ``_`` で
                構成する。``"studio.myTool"`` のように途中へ ``.`` を入れて階層を
                表してもよいが、先頭・末尾に置いたり連続させたりはできない。
            defaults (Mapping[str, object] | None): キーごとのデフォルト値。
                ここで JSON へ変換できるか検査し、変換後のテキストとして保持する。

        Raises:
            TypeError: prefix が文字列でない場合。defaults のキーが文字列でない場合や、
                値に JSON で表せない型・文字列以外の ``dict`` キーを含む場合。
            ValueError: prefix やキーの書式が不正な場合。defaults の値に
                NaN・無限大・循環参照を含む場合や、入れ子が深すぎる場合。
        """
        _validate_prefix(prefix)
        self._prefix = prefix
        self._default_texts = {}
        source = {} if defaults is None else dict(defaults)
        for key, value in source.items():
            _validate_key(key)
            self._default_texts[key] = _to_json(value)

    def __repr__(self):
        """デバッグ用の表現を返す。

        Returns:
            str: ``OptionVar('<prefix>')`` 形式の文字列。
        """
        return "{}({!r})".format(type(self).__name__, self._prefix)

    @property
    def prefix(self):
        """str: optionVar 名の先頭に付ける接頭辞。区切りの ``.`` は含まない。"""
        return self._prefix

    @property
    def defaults(self):
        """dict[str, object]: キーごとのデフォルト値。参照するたびに新しい辞書を返す。"""
        return {key: json.loads(text) for key, text in self._default_texts.items()}

    def full_name(self, key):
        """キーに対応する optionVar 名を組み立てる。Maya への問い合わせは行わない。

        Args:
            key (str): 設定のキー。

        Returns:
            str: ``"<prefix>.<key>"`` 形式の optionVar 名。

        Raises:
            TypeError: key が文字列でない場合。
            ValueError: key が空、または ASCII の英数字と ``_`` 以外の文字を含む場合。
        """
        _validate_key(key)
        return self._prefix + _SEPARATOR + key

    # ------------------------------------------------------------------
    # 読み出し
    # ------------------------------------------------------------------
    def get(self, key, fallback=None):
        """キーの現在の値を取得する。

        Args:
            key (str): 設定のキー。
            fallback (object): 保存済みの値もデフォルト値も無い場合に返す値。

        Returns:
            object: 保存済みの値。無ければデフォルト値、それも無ければ fallback。

        Raises:
            TypeError: key が文字列でない場合。
            ValueError: key が空、または ASCII の英数字と ``_`` 以外の文字を含む場合。
        """
        value = self._resolve(key)
        return fallback if value is _MISSING else value

    def __getitem__(self, key):
        """``store[key]`` でキーの現在の値を取得する。

        Args:
            key (str): 設定のキー。

        Returns:
            object: 保存済みの値。無ければデフォルト値。

        Raises:
            KeyError: 保存済みの値もデフォルト値も無い場合。
            TypeError: key が文字列でない場合。
            ValueError: key が空、または ASCII の英数字と ``_`` 以外の文字を含む場合。
        """
        value = self._resolve(key)
        if value is _MISSING:
            raise KeyError(key)
        return value

    def __contains__(self, key):
        """``key in store`` で値を取得できるキーか判定する。

        キーとして使えない値(文字列以外や、使えない文字を含む文字列)には
        例外を送出せず False を返す。

        Args:
            key (object): 判定するキー。

        Returns:
            bool: 保存済みの値かデフォルト値があれば True。
        """
        try:
            _validate_key(key)
        except (TypeError, ValueError):
            return False
        return self._resolve(key) is not _MISSING

    def is_stored(self, key):
        """キーに読み出せる値が保存されているか問い合わせる。

        デフォルト値の有無は考慮しない。JSON として読めない optionVar は
        保存されていないものとみなす。

        Args:
            key (str): 設定のキー。

        Returns:
            bool: 読み出せる値が optionVar に保存されていれば True。

        Raises:
            TypeError: key が文字列でない場合。
            ValueError: key が空、または ASCII の英数字と ``_`` 以外の文字を含む場合。
        """
        return self._read_stored(key) is not _MISSING

    def stored_keys(self):
        """読み出せる値が保存されているキーを列挙する。

        接頭辞の直下にある optionVar だけが対象で、``<prefix>.<子>.<キー>`` のような
        さらに下の階層、キーの規則に合わない名前、JSON として読めない optionVar は
        含めない。

        Returns:
            list[str]: キー名の昇順リスト。
        """
        return sorted(self._stored_values())

    def keys(self):
        """値を取得できるキー(保存済みの値かデフォルト値を持つもの)を列挙する。

        Returns:
            list[str]: キー名の昇順リスト。
        """
        return sorted(set(self._stored_values()).union(self._default_texts))

    def values(self):
        """:meth:`keys` の順に現在の値を列挙する。

        Returns:
            list[object]: 各キーの現在の値。
        """
        return list(self.to_dict().values())

    def items(self):
        """:meth:`keys` の順にキーと現在の値の組を列挙する。

        Returns:
            list[tuple[str, object]]: ``(キー, 値)`` のリスト。
        """
        return list(self.to_dict().items())

    def to_dict(self):
        """全キーの現在の値を、保存済みの値を優先して辞書にまとめる。

        Returns:
            dict[str, object]: キー名の昇順に並べた辞書。値は毎回新しく作られる。
        """
        merged = self.defaults
        merged.update(self._stored_values())
        return {key: merged[key] for key in sorted(merged)}

    def __iter__(self):
        """``for key in store`` で :meth:`keys` の結果を順に返す。

        Returns:
            Iterator[str]: キー名のイテレータ。
        """
        return iter(self.keys())

    def __len__(self):
        """``len(store)`` で :meth:`keys` の件数を返す。

        Returns:
            int: 値を取得できるキーの数。
        """
        return len(self.keys())

    # ------------------------------------------------------------------
    # 書き込み・削除
    # ------------------------------------------------------------------
    def set(self, key, value):
        """値を JSON テキストへ変換して optionVar に保存する。

        デフォルト値と同じ値であっても保存する。

        Args:
            key (str): 設定のキー。
            value (object): 保存する値。JSON で表せるものに限る。

        Raises:
            TypeError: key が文字列でない場合。value に JSON で表せない型や
                文字列以外の ``dict`` キーを含む場合。
            ValueError: key が空、または ASCII の英数字と ``_`` 以外の文字を含む場合。
                value に NaN・無限大・循環参照を含む場合や、入れ子が深すぎる場合。
        """
        name = self.full_name(key)
        cmds.optionVar(stringValue=(name, _to_json(value)))

    def __setitem__(self, key, value):
        """``store[key] = value`` で :meth:`set` と同じく値を保存する。

        Args:
            key (str): 設定のキー。
            value (object): 保存する値。JSON で表せるものに限る。

        Raises:
            TypeError: :meth:`set` と同じ条件。
            ValueError: :meth:`set` と同じ条件。
        """
        self.set(key, value)

    def update(self, values):
        """複数のキーをまとめて保存する。

        先に全てのキーと値を検査し、1 つでも不正なものがあれば何も書き込まない。

        Args:
            values (Mapping[str, object]): 保存するキーと値。

        Raises:
            TypeError: :meth:`set` と同じ条件。
            ValueError: :meth:`set` と同じ条件。
        """
        pending = [(self.full_name(key), _to_json(value)) for key, value in dict(values).items()]
        for name, text in pending:
            cmds.optionVar(stringValue=(name, text))

    def reset(self, key):
        """保存済みの値を削除し、デフォルト値(無ければ未設定)の状態へ戻す。

        JSON として読めない optionVar が同じ名前で残っていれば、それも削除する。

        Args:
            key (str): 設定のキー。

        Returns:
            bool: optionVar を削除した場合は True、元から無かった場合は False。

        Raises:
            TypeError: key が文字列でない場合。
            ValueError: key が空、または ASCII の英数字と ``_`` 以外の文字を含む場合。
        """
        name = self.full_name(key)
        if not cmds.optionVar(exists=name):
            return False
        cmds.optionVar(remove=name)
        return True

    def __delitem__(self, key):
        """``del store[key]`` で保存済みの値を削除する。

        :meth:`reset` と違い、読み出せる値が保存されていなければ KeyError を送出する。
        削除後もデフォルト値があれば、``store[key]`` はデフォルト値を返す。

        Args:
            key (str): 設定のキー。

        Raises:
            KeyError: 読み出せる値が保存されていない場合。
            TypeError: key が文字列でない場合。
            ValueError: key が空、または ASCII の英数字と ``_`` 以外の文字を含む場合。
        """
        if not self.is_stored(key):
            raise KeyError(key)
        cmds.optionVar(remove=self.full_name(key))

    def reset_all(self):
        """接頭辞の直下にある optionVar を全て削除する。

        JSON として読めない optionVar も削除する。``<prefix>.<子>.<キー>`` のような
        下の階層の optionVar と、キーの規則に合わない名前の optionVar は対象外。
        デフォルト値はそのまま残る。

        Returns:
            list[str]: 削除した optionVar のキー名(昇順)。
        """
        removed = []
        for key, name in self._scoped_names():
            cmds.optionVar(remove=name)
            removed.append(key)
        return removed

    # ------------------------------------------------------------------
    # 内部処理
    # ------------------------------------------------------------------
    def _resolve(self, key):
        """保存済みの値、無ければデフォルト値を返す。どちらも無ければ _MISSING。"""
        value = self._read_stored(key)
        if value is _MISSING and key in self._default_texts:
            value = json.loads(self._default_texts[key])
        return value

    def _read_stored(self, key):
        """キーの optionVar を読んで JSON を解釈する。無い・読めない場合は _MISSING。"""
        name = self.full_name(key)
        if not cmds.optionVar(exists=name):
            return _MISSING
        return _from_json(cmds.optionVar(query=name))

    def _scoped_names(self):
        """接頭辞の直下にある optionVar を ``(キー, optionVar 名)`` の昇順リストで返す。

        キーの規則に合う名前だけを返す(区切り文字を含む下の階層もここで除かれる)。
        """
        head = self._prefix + _SEPARATOR
        found = []
        for name in cmds.optionVar(list=True) or []:
            if not name.startswith(head):
                continue
            key = name[len(head):]
            if _NAME_PART.fullmatch(key):
                found.append((key, name))
        found.sort()
        return found

    def _stored_values(self):
        """接頭辞の直下で読み出せる値を ``{キー: 値}`` にまとめる。"""
        values = {}
        for key, name in self._scoped_names():
            value = _from_json(cmds.optionVar(query=name))
            if value is not _MISSING:
                values[key] = value
        return values


def _validate_prefix(prefix):
    """接頭辞として使える文字列か検査する。

    ``.`` で区切った各部分が、ASCII の英数字と ``_`` からなる 1 文字以上の
    文字列であることを求める。

    Args:
        prefix (object): 検査する値。

    Raises:
        TypeError: 文字列でない場合。
        ValueError: 空の場合。``.`` が先頭・末尾にあるか連続している場合。
            ASCII の英数字・``_``・``.`` 以外の文字を含む場合。
    """
    if not isinstance(prefix, str):
        raise TypeError("prefix must be str, not {}".format(type(prefix).__name__))
    if not prefix:
        raise ValueError("prefix must not be empty")
    for part in prefix.split(_SEPARATOR):
        if not part:
            raise ValueError("prefix {!r} has an empty segment around '{}'".format(prefix, _SEPARATOR))
        if not _NAME_PART.fullmatch(part):
            raise ValueError(
                "prefix {!r} may only contain ASCII letters, digits, '_' and '{}'".format(prefix, _SEPARATOR)
            )


def _validate_key(key):
    """キーとして使える文字列か検査する。

    Args:
        key (object): 検査する値。

    Raises:
        TypeError: 文字列でない場合。
        ValueError: 空、または ASCII の英数字と ``_`` 以外の文字(``.`` を含む)を含む場合。
    """
    if not isinstance(key, str):
        raise TypeError("key must be str, not {}".format(type(key).__name__))
    if not key:
        raise ValueError("key must not be empty")
    if not _NAME_PART.fullmatch(key):
        raise ValueError("key {!r} may only contain ASCII letters, digits and '_'".format(key))


def _to_json(value):
    """値を optionVar に保存する JSON テキストへ変換する。

    ``json.dumps`` は数値や ``None`` の ``dict`` キーを黙って文字列へ変えるため、
    変換後に全ての ``dict`` キーが ``str`` であることを別途確かめる
    (先に ``json.dumps`` を通すことで、循環参照が無いことは保証済み)。
    入れ子が深すぎて ``json.dumps`` が RecursionError を送出した場合は、
    他の不正な値と同じく ValueError として呼び出し元へ伝える。

    Args:
        value (object): 変換する値。

    Returns:
        str: ASCII だけで構成された、空白を含まない JSON テキスト。

    Raises:
        TypeError: JSON で表せない型、または文字列以外の ``dict`` キーを含む場合。
        ValueError: NaN・無限大・循環参照を含む場合、または入れ子が深すぎて
            変換できない場合。
    """
    try:
        text = json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    except RecursionError:
        raise ValueError("value is nested too deeply to be encoded as JSON")
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            for child_key, child in item.items():
                if not isinstance(child_key, str):
                    raise TypeError("dict keys must be str, got {!r}".format(child_key))
                pending.append(child)
        elif isinstance(item, (list, tuple)):
            pending.extend(item)
    return text


def _reject_non_finite(token):
    """JSON 拡張の ``NaN``/``Infinity``/``-Infinity`` を読み込み時に拒否する。"""
    raise ValueError("non-finite number {} is not accepted".format(token))


def _parse_finite_float(token):
    """JSON の小数表記を ``float`` にし、範囲を超えて無限大になるものは拒否する。

    ``1e400`` のような表記は ``float()`` で無限大になるため、``parse_constant`` だけでは
    防げない。書き込み側(``allow_nan=False``)と同じく有限値だけを受け付ける。
    """
    number = float(token)
    if not math.isfinite(number):
        raise ValueError("number {} is out of the float range".format(token))
    return number


def _from_json(raw):
    """optionVar から取得した生の値を JSON として解釈する。

    Args:
        raw (object): ``cmds.optionVar(query=...)`` の戻り値。

    Returns:
        object: 解釈した値。文字列でない場合、JSON として読めない場合、
        有限でない数値を含む場合、入れ子が深すぎて解釈できない場合は _MISSING。
    """
    if not isinstance(raw, str):
        return _MISSING
    try:
        return json.loads(raw, parse_constant=_reject_non_finite, parse_float=_parse_finite_float)
    except (ValueError, RecursionError):
        # RecursionError は、他の手段で極端に深い入れ子の配列・オブジェクトが
        # 書き込まれていた場合に json.loads から送出される。
        return _MISSING
