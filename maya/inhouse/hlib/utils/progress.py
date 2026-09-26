"""ループの経過をテキスト1行で表示する進捗表示。

Maya に依存しない純粋な Python 実装。GUI のプログレスバーではなく、
テキストストリーム(既定では呼び出し時点の ``sys.stdout``)へ行を書き出す。
描画のたびに同じ文字列を ``notify`` コールバックへ渡せるため、Slack など
外部サービスへ経過を中継する接続点としても使える。

件数が分かる場合の表示例(``label="export"``、``width=20``、20件中9件処理済み)::

    export |=========-----------|  45% 9/20

件数が分からない場合(``len()`` を持たないイテレーターで ``total`` 未指定)::

    export 9/?
"""

import sys

_DONE_CELL = "="
_TODO_CELL = "-"
_FRAME = "|"
_UNKNOWN_TOTAL = "?"


def _proportion(done, total, scale):
    """処理済み件数を 0 から scale までの整数へ換算する。

    浮動小数点の丸め誤差で値が1つ小さくなるのを避けるため、整数演算で
    切り捨てる。全体が0件の場合や、処理済み件数が全体に達した・超えた
    場合は scale に揃える。

    Args:
        done (int): 処理済みの件数。
        total (int): 全体の件数。
        scale (int): 換算後の最大値。

    Returns:
        int: 0 以上 scale 以下の整数。
    """
    if total <= 0 or done >= total:
        return scale
    return done * scale // total


class _ProgressLine(object):
    """1本の進捗行について、件数の保持・文字列の組み立て・出力を受け持つ。

    処理済みの件数は ``done`` に保持し、``advance`` のたびに1つ増やす。
    見出しは生成時に末尾の空白を取り除いた形で保持し、空なら表示しない。

    Args:
        label (str): 行頭の見出し。
        total (int | None): 全体の件数。不明なら None。
        width (int): バー部分の文字数。
        stream (TextIO): ``write`` を備える出力先。
        notify (Callable[[str], object] | None): 描画した文字列の通知先。
    """

    def __init__(self, label, total, width, stream, notify):
        self.label = label.rstrip()
        self.total = total
        self.width = width
        self.stream = stream
        self.notify = notify
        self.done = 0

    def render(self):
        """現在の件数に応じた表示文字列を組み立てる。

        Returns:
            str: 件数が既知ならバー・百分率・件数、不明なら件数だけを並べた文字列。
                行頭復帰や改行は含まない。
        """
        if self.total is None:
            body = f"{self.done}/{_UNKNOWN_TOTAL}"
        else:
            cells = _proportion(self.done, self.total, self.width)
            bar = _DONE_CELL * cells + _TODO_CELL * (self.width - cells)
            percent = _proportion(self.done, self.total, 100)
            body = f"{_FRAME}{bar}{_FRAME} {percent:>3d}% {self.done}/{self.total}"
        if self.label:
            return f"{self.label} {body}"
        return body

    def draw(self):
        """行頭へ戻って現在の表示で上書きし、通知先があれば同じ文字列を渡す。

        Returns:
            str: 出力した表示文字列。
        """
        text = self.render()
        self.stream.write("\r" + text)
        self._flush()
        if self.notify is not None:
            self.notify(text)
        return text

    def advance(self):
        """処理済み件数を1つ進めて描画し直す。"""
        self.done += 1
        self.draw()

    def finish(self, quiet=False):
        """改行を出力して行を閉じる。

        Args:
            quiet (bool): True なら、改行の書き込みや ``flush`` で起きた
                ``Exception`` を送出せずに捨てる。別の例外が伝わっている
                途中で行を閉じるときに使い、元の例外が後から起きた出力先の
                失敗で置き換わらないようにする。
        """
        try:
            self.stream.write("\n")
            self._flush()
        except Exception:
            if not quiet:
                raise

    def _flush(self):
        """出力先が ``flush`` を持つ場合だけ呼び出す。"""
        flush = getattr(self.stream, "flush", None)
        if flush is not None:
            flush()


def _track(iterable, line):
    """要素を順に返しながら、line の件数更新と描画を行うジェネレーター。

    最初の要素を取り出せた時点で0件の行を描画し、利用側が次の要素を
    要求するたび(=直前の要素の処理が終わるたび)に1件進める。途中で
    ``break`` した場合や例外でジェネレーターが閉じられた場合も、描画に
    着手していれば改行で行を閉じる。描画そのもの(出力や ``notify``)が
    例外を送出した場合も同様で、書きかけの行を改行で閉じてから例外を
    伝える。要素が1つも無ければ何も出力しない。

    例外が伝わっている途中で行を閉じる場合、改行の書き込みに失敗しても
    その失敗は捨て、先に起きた例外をそのまま伝える(閉じられた出力先へ
    もう一度書こうとして別の例外に置き換わるのを防ぐ)。最後まで反復
    できた場合の改行の失敗は、そのまま呼び出し側へ伝える。

    Args:
        iterable (Iterable): 反復する対象。
        line (_ProgressLine): 描画を担当する進捗行。

    Yields:
        object: iterable の要素をそのまま返す。
    """
    started = False
    try:
        for item in iterable:
            if not started:
                # 描画の途中で例外が出ても行を閉じられるよう、描画より先に立てる。
                started = True
                line.draw()
            yield item
            line.advance()
    except BaseException:
        # GeneratorExit(break による close)や KeyboardInterrupt も含め、伝わっている例外を優先する。
        if started:
            line.finish(quiet=True)
        raise
    if started:
        line.finish()


def progress_bar(iterable, *, label="", total=None, width=30, stream=None, notify=None):
    """要素をそのまま返しつつ、処理の進み具合を1行で表示するイテレーターを作る。

    ``for`` 文の対象を包むだけで使える。表示は「処理済みの件数」を基準にし、
    ループ本体が1回終わって次の要素が要求されるたびに1件進む。最初の要素を
    取り出した時点で0件の状態を描画し、最後まで反復したときに改行で行を閉じる。
    ``break`` などで途中で抜けた場合は、返り値のジェネレーターが ``close()``
    されるか回収された時点で行を閉じる(このときの改行の書き込み失敗は無視する)。要素が1つも無い場合は何も出力せず、``notify`` も
    呼ばない。ループ本体・出力先・``notify`` のいずれかで例外が起きた
    場合はその例外をそのまま伝え、行を閉じる改行の書き込みが続けて
    失敗しても元の例外を置き換えない。

    行の更新は行頭復帰(``\\r``)による上書きで行う。Maya の Script Editor
    のように行頭復帰を解釈しない出力先では、描画ごとの文字列が上書きされず
    順に残る場合がある。

    引数の検証と ``len()`` による件数の取得は呼び出し時に行い、要素の
    取り出しと描画は返り値を反復したときに行う。

    Args:
        iterable (Iterable): 進捗を表示しながら反復する対象。
        label (str): 行頭に付ける見出し。文字列のみ受け付ける。末尾の空白は
            取り除き、バーとの間に空白を1つ挟む。空文字(または空白だけ)なら
            見出しを付けない。
        total (int | None): 全体の件数。None なら ``len(iterable)`` を試み、
            ``len()`` を持たない場合は件数不明として、バーと百分率を省いて
            処理済み件数だけを表示する。実際の要素数が total を超えた場合、
            バーと百分率は満杯のまま件数だけが増える。
        width (int): バー部分の文字数。1以上の整数。
        stream (TextIO | None): ``write`` を備える出力先。``flush`` を持つ
            場合は描画のたびに呼ぶ。None なら呼び出し時点の ``sys.stdout``
            (``contextlib.redirect_stdout`` の差し替え先も含む)を使う。
        notify (Callable[[str], object] | None): 行を描画するたびに、その
            表示文字列(行頭復帰と改行を含まない)を受け取るコールバック。
            戻り値は無視する。要素数と同程度の回数呼ばれるため、外部サービス
            へ送る場合は必要に応じて呼び出し側で間引く。

    Returns:
        Iterator: iterable の要素を同じ順序でそのまま返すイテレーター。

    Raises:
        TypeError: label が文字列でない場合、width が整数でない場合、
            または total が None でも整数でもない場合。
        ValueError: width が1未満の場合、または total が負の場合。

    Examples:
        >>> import io
        >>> buffer = io.StringIO()
        >>> list(progress_bar("ab", label="demo", width=4, stream=buffer))
        ['a', 'b']
        >>> buffer.getvalue().split("\\r")[-1]
        'demo |====| 100% 2/2\\n'
    """
    if not isinstance(label, str):
        raise TypeError(f"label must be a str, got {type(label).__name__}")

    if isinstance(width, bool) or not isinstance(width, int):
        raise TypeError(f"width must be an int, got {type(width).__name__}")
    if width < 1:
        raise ValueError(f"width must be 1 or greater, got {width}")

    if total is None:
        try:
            total = len(iterable)
        except TypeError:
            total = None
    elif isinstance(total, bool) or not isinstance(total, int):
        raise TypeError(f"total must be an int or None, got {type(total).__name__}")
    elif total < 0:
        raise ValueError(f"total must not be negative, got {total}")

    if stream is None:
        stream = sys.stdout

    line = _ProgressLine(label, total, width, stream, notify)
    return _track(iterable, line)
