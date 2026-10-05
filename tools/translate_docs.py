"""Sphinx ドキュメントの文を、ローカルの LLM(Ollama)で英訳して .po に保存する。

使い方(リポジトリ直下から。Sphinx が入った Python で実行する)::

    python tools/translate_docs.py hedit hrig            # 未訳の文だけ英訳する
    python tools/translate_docs.py hedit --limit 20      # 試しに20件だけ
    python tools/translate_docs.py hedit --check         # 英訳せず、未訳の件数と英語版のビルドだけ確かめる

流れ:

1. ``sphinx-build -b gettext`` で本文の文を取り出す(``maya/inhouse/<名前>/docs``)。
2. ``docs/locale/en/LC_MESSAGES/docs.po`` を、取り出した文に合わせて更新する(消えた文は削除、新しい文は未訳で追加)。
3. 未訳の文を Ollama の ``qwen3-coder:30b`` で英訳する。reStructuredText の記法(````code````・``:ref:`` など)が
   崩れた訳は使わず、未訳のまま残す(英語版では日本語のまま出る)。10件ごとに保存するので、途中で止めても続きから再開できる。
4. 英語版を ``-W`` でビルドして、警告が無いことを確かめる。
5. 最後にモデルを GPU から下ろす(Maya と GPU を取り合わないように)。

CI(``.github/workflows/hlib-docs.yml``)は保存した .po を使って英語版をビルドするだけで、LLM は使わない。
GPU のメモリを約18GB使うため、Maya を使っていないときに実行する(CLAUDE.md の例外の決まり)。
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import urllib.request

from babel.messages.catalog import Catalog
from babel.messages.pofile import read_po, write_po

ROOT = Path(__file__).resolve().parents[1]
OLLAMA = 'http://127.0.0.1:11434/api/'
DEFAULT_MODEL = 'qwen3-coder:30b'

#: 用語集(日本語 → 英語)。同じ言葉を毎回同じ英語にする。
GLOSSARY = {
    'アトリビュート': 'attribute', 'ノード': 'node', 'プラグ': 'plug', 'ジョイント': 'joint', 'リグ': 'rig',
    'コンストレイント': 'constraint', '拘束': 'constraint', 'ウェイト': 'weight', 'スキン': 'skin',
    'コントローラー': 'controller', 'シーン': 'scene', '名前空間': 'namespace',
    '出力欄': 'output panel', 'コード欄': 'code editor', '入力欄': 'input editor', 'タブ': 'tab',
    '補完': 'completion', '補完候補': 'completion candidates', 'ホバー': 'hover', '静的解析': 'static analysis',
    '構文チェック': 'syntax check', '問題一覧': 'Problems list', 'スペルチェック': 'spell check',
    '折りたたみ': 'folding', '見出しの固定表示': 'sticky scroll', '定義へ移動': 'Go to definition',
    '定義をその場で見る': 'Peek definition', '記号へ移動': 'Go to symbol', '引数のヒント': 'parameter hints',
    '保存前との差分': 'compare with saved', '同じ名前の強調': 'word highlight', 'スクロールバーの印': 'scroll bar markers',
    'アウトライン': 'Outline', 'ドック': 'dock', '自動保存': 'autosave', '復元': 'restore',
    'プラグイン': 'plug-in', 'ロード': 'load', 'アンロード': 'unload', '信頼済みの場所': 'trusted locations',
}

SYSTEM_PROMPT = (
    'You translate Japanese technical documentation into natural, concise English. '
    'The text is a fragment of a Sphinx reStructuredText document about Autodesk Maya tools '
    '(the "hlib" Maya API library, the "hedit" Python/MEL script editor, and the "hrig" rigging library).\n'
    'Rules:\n'
    '1. Output only the English translation of the given fragment. No explanations, no quotes, no code fences.\n'
    '2. Keep every reStructuredText construct exactly as it is: ``inline literals``, :role:`targets` '
    '(for example :ref:`label`, :doc:`page`), `link text <url>`_, **strong**, *emphasis*, |substitutions|, '
    'and backslash escapes such as "\\ ". Never translate or change the content of ``inline literals``.\n'
    '3. Keep code, identifiers, file paths, command names, key names (Ctrl+Enter), menu labels that are '
    'already English (File, Edit > Preferences) and numbers unchanged.\n'
    '4. Keep line breaks only where the source has a list or table structure; otherwise you may reflow.\n'
    '5. Placeholders such as [[C0]] stand for code. Copy each placeholder exactly once, unchanged, at the '
    'grammatically right place.\n'
    '6. Use these term translations: ' + '; '.join('{} = {}'.format(k, v) for k, v in GLOSSARY.items()) + '.'
)

_JAPANESE = re.compile(r'[぀-ヿ㐀-鿿！-｠]')
_LITERAL = re.compile(r'``.+?``')
_ROLE = re.compile(r':[\w:+-]+:`')
_URL = re.compile(r'<(https?://[^>]+)>')
_INLINE = re.compile(r'``.+?``|\*\*[^*]+?\*\*|:[\w:+-]+:`[^`]+`|`[^`]+`__?')


def ollama(path, payload, timeout=600):
    """Ollama の HTTP API を呼ぶ。

    Args:
        path (str): ``chat``・``generate`` など。
        payload (dict): 送る JSON。
        timeout (float): 待つ秒数。

    Returns:
        dict: 応答の JSON。
    """
    request = urllib.request.Request(OLLAMA + path, data=json.dumps(payload).encode('utf-8'),
                                     headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def clean(text):
    """モデルの応答から、余計な囲み(引用符・コードの囲み・前置き)を除く。

    Args:
        text (str): 応答。

    Returns:
        str: 訳文。
    """
    text = text.strip()
    text = re.sub(r'^```[a-z]*\n|\n```$', '', text).strip()
    text = re.sub(r'^(Translation|English)\s*:\s*', '', text, flags=re.IGNORECASE)
    return text


def fix_boundaries(text):
    """インラインの記法が英字に接していれば ``\\ `` を入れる(接していると reStructuredText の記法にならない)。

    Args:
        text (str): 訳文。

    Returns:
        str: 直した訳文。
    """
    result = []
    position = 0
    for match in _INLINE.finditer(text):
        start, end = match.span()
        result.append(text[position:start])
        before = text[start - 1] if start > 0 else ' '
        after = text[end] if end < len(text) else ' '
        if before.isalnum() and not text[max(0, start - 2):start] == '\\ ':
            result.append('\\ ')
        result.append(match.group(0))
        if after.isalnum():
            result.append('\\ ')
        position = end
    result.append(text[position:])
    return ''.join(result)


#: 単語の末尾の _ のうち、後ろが空白・句読点・文末のもの(reStructuredText ではリンクの参照になる)。
_TRAILING_UNDERSCORE = re.compile(r'(?<=[A-Za-z0-9])_(?=[\s.,;:!?)]|$)')


def escape_references(source, translation):
    """訳文で新しく参照の記法になってしまう ``word_`` の ``_`` を ``\\_`` にする。

    日本語の原文では ``shelf_名前`` のように _ の後ろに文字が続くので参照にならないが、英訳で
    ``shelf_ name`` となると参照になり、英語版のビルドがエラーになる。インラインのコードの中は変えない。

    Args:
        source (str): 原文。
        translation (str): 訳文。

    Returns:
        str: 直した訳文。原文にも同じ参照がある場合は変えない。
    """
    if _TRAILING_UNDERSCORE.search(_PROTECTED.sub('', source)):
        return translation  # 原文に参照がある(意図した参照)。
    result = []
    position = 0
    for match in _PROTECTED.finditer(translation):
        result.append(_TRAILING_UNDERSCORE.sub(r'\\_', translation[position:match.start()]))
        result.append(match.group(0))
        position = match.end()
    result.append(_TRAILING_UNDERSCORE.sub(r'\\_', translation[position:]))
    return ''.join(result)


def valid(source, translation):
    """訳文が使えるか(記法が保たれ、日本語が残っていないか)。

    Args:
        source (str): 原文。
        translation (str): 訳文。

    Returns:
        str: 問題の説明。問題が無ければ空。
    """
    if not translation:
        return 'empty'
    # コードの部分(``<Mayaの年>`` など)の日本語は訳さないので数えない。
    if _JAPANESE.search(_PROTECTED.sub('', translation)):
        return 'Japanese left in the translation'
    # 原文のコード・ロールが全て残っていればよい(モデルが名前をコードの記法で囲み足すのは許す)。
    translated_literals = _LITERAL.findall(translation)
    for literal in _LITERAL.findall(source):
        if literal not in translated_literals:
            return 'inline literals changed'
        translated_literals.remove(literal)
    if sorted(_ROLE.findall(source)) != sorted(_ROLE.findall(translation)):
        return 'roles changed'
    if sorted(_URL.findall(source)) != sorted(_URL.findall(translation)):
        return 'links changed'
    if source.count('**') != translation.count('**'):
        return 'strong markup changed'
    return ''


#: 訳させない部分(インラインのコード・ロール・リンクの URL・置換)。目印に置き換えてから訳させる。
_PROTECTED = re.compile(r'``.+?``|:[\w:+-]+:`[^`]+`|<https?://[^>]+>|\|[^|\s]+\|')


def protect(source):
    """訳させない部分を ``[[C0]]`` のような目印に置き換える(モデルが中身を書き換えないように)。

    Args:
        source (str): 原文。

    Returns:
        tuple[str, list[str]]: (置き換えた文, 元の部分の一覧)。
    """
    parts = []

    def replace(match):
        parts.append(match.group(0))
        return '[[C{}]]'.format(len(parts) - 1)
    return _PROTECTED.sub(replace, source), parts


def restore(text, parts):
    """目印を元の部分に戻す。

    Args:
        text (str): 訳文。
        parts (list[str]): protect が返した元の部分。

    Returns:
        str: 戻した訳文。目印が欠けたり増えたりしていれば空。
    """
    # モデルが目印をさらにコードの記法(``[[C0]]``・`[[C0]]`)や引用符で囲むことがあるので外す。
    text = re.sub(r'(``|`|"|\')(\[\[C\d+\]\])\1', r'\2', text)
    for index, part in enumerate(parts):
        token = '[[C{}]]'.format(index)
        if text.count(token) != 1:
            return ''
        text = text.replace(token, part)
    return '' if re.search(r'\[\[C\d+\]\]', text) else text


def translate(model, source):
    """1つの文を英訳する。記法が崩れたら最大3回言い直させる。

    Args:
        model (str): Ollama のモデル名。
        source (str): 原文。

    Returns:
        tuple[str, str]: (訳文, 問題の説明)。使えない訳なら訳文は空。
    """
    protected, parts = protect(source)
    messages = [{'role': 'system', 'content': SYSTEM_PROMPT}, {'role': 'user', 'content': protected}]
    problem = ''
    for attempt in range(4):
        # 最初は毎回同じ訳になるよう temperature 0。言い直しでは少し揺らぎを足す。
        # 長文の反復生成でGPUを占有し続けないよう、1応答の長さを制限する。
        options = {'temperature': 0 if attempt == 0 else 0.4, 'seed': 42 + attempt,
                   'num_ctx': 8192, 'num_predict': 2048}
        reply = ollama('chat', {'model': model, 'messages': messages, 'stream': False, 'keep_alive': '15m',
                                'options': options})
        # 段落の中の改行は意味を持たないので空白にまとめる(改行の後の字下げや記号が、リスト・見出しの記法に見えないように)。
        answer = re.sub(r'\s*\n\s*', ' ', clean(reply['message']['content']))
        # 原文の日本語の記号(・、。()など)が残っていれば英語の記号にする。
        for japanese, english in (('・', ', '), ('、', ', '), ('。', '. '), ('（', ' ('), ('）', ') '), ('：', ': '),
                                  ('「', '"'), ('」', '"'), ('　', ' ')):
            answer = answer.replace(japanese, english)
        answer = re.sub(r' {2,}', ' ', answer).strip()
        translation = escape_references(source, fix_boundaries(restore(answer, parts)))
        problem = ('output limit reached' if reply.get('done_reason') == 'length'
                   else valid(source, translation) if translation else 'placeholders changed')
        translation_for_retry = answer
        if not problem:
            return translation, ''
        messages += [{'role': 'assistant', 'content': translation_for_retry},
                     {'role': 'user', 'content': 'The translation is not usable ({}). Translate the original '
                                                 'fragment again. Keep every placeholder such as [[C0]] exactly '
                                                 'once and keep the reStructuredText markup.'.format(problem)}]
    return '', problem


def extract(docs, directory):
    """gettext で文を取り出す。

    Args:
        docs (Path): ドキュメントのフォルダー(conf.py のある所)。
        directory (Path): 取り出し先。

    Returns:
        Catalog: 取り出した文(docs.pot)。
    """
    subprocess.run([sys.executable, '-m', 'sphinx', '-q', '-E', '-b', 'gettext', str(docs), str(directory)], check=True)
    with (directory / 'docs.pot').open('rb') as handle:
        return read_po(handle)


def load_catalog(path, template):
    """保存済みの .po を読み、取り出した文に合わせて更新する。

    Args:
        path (Path): docs.po。
        template (Catalog): 取り出した文。

    Returns:
        Catalog: 更新した .po。
    """
    if path.exists():
        with path.open('rb') as handle:
            catalog = read_po(handle, locale='en')
    else:
        catalog = Catalog(locale='en', project=template.project)
    catalog.update(template, no_fuzzy_matching=True)
    catalog.obsolete.clear()
    for message in catalog:
        if message.id and isinstance(message.string, str) and '\n' in message.string:
            # 段落の中の改行は空白にまとめる(改行の後の記号がリスト・見出しの記法に見えないように)。
            message.string = re.sub(r'\s*\n\s*', ' ', message.string)
        if message.id and isinstance(message.string, str) and message.string:
            message.string = escape_references(message.id, message.string)
    return catalog


def save_catalog(path, catalog):
    """.po を書く(折り返さず、行番号を書かないので差分が小さい)。

    Args:
        path (Path): docs.po。
        catalog (Catalog): 書く内容。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('wb') as handle:
        write_po(handle, catalog, width=0, omit_header=False, ignore_obsolete=True, include_previous=False,
                 no_location=True)


def build_english(docs, directory):
    """英語版を -W でビルドする。

    Args:
        docs (Path): ドキュメントのフォルダー。
        directory (Path): 出力先。

    Returns:
        subprocess.CompletedProcess: 結果(警告があれば returncode が0以外)。
    """
    return subprocess.run([sys.executable, '-m', 'sphinx', '-q', '-E', '-a', '-b', 'html', '-W', '--keep-going',
                           '-D', 'language=en', str(docs), str(directory)], capture_output=True, text=True,
                          encoding='utf-8', errors='replace')


def main():
    """コマンドラインの入口。"""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('names', nargs='+', help='maya/inhouse の下のドキュメント名(hedit・hrig など)')
    parser.add_argument('--model', default=DEFAULT_MODEL)
    parser.add_argument('--limit', type=int, default=0, help='英訳する最大の件数(0なら全部)')
    parser.add_argument('--check', action='store_true', help='英訳せず、未訳の件数とビルドだけ確かめる')
    args = parser.parse_args()
    failed_build = False
    used_model = False
    try:
        for name in args.names:
            docs = ROOT / 'maya/inhouse' / name / 'docs'
            po_path = docs / 'locale/en/LC_MESSAGES/docs.po'
            with tempfile.TemporaryDirectory() as temporary:
                catalog = load_catalog(po_path, extract(docs, Path(temporary) / 'gettext'))
            pending = [message for message in catalog if message.id and _JAPANESE.search(message.id)
                       and (not message.string or message.fuzzy)]
            print('{}: {} messages, {} untranslated'.format(name, len([m for m in catalog if m.id]), len(pending)),
                  flush=True)
            skipped = []
            if not args.check:
                if args.limit:
                    pending = pending[:args.limit]
                start = time.perf_counter()
                for index, message in enumerate(pending, 1):
                    used_model = True
                    translation, problem = translate(args.model, message.id)
                    if translation:
                        message.string = translation
                        message.flags.discard('fuzzy')
                    else:
                        skipped.append((message.id, problem))
                    if index % 10 == 0 or index == len(pending):
                        save_catalog(po_path, catalog)
                        print('  {}/{} ({:.0f}s)'.format(index, len(pending), time.perf_counter() - start), flush=True)
            save_catalog(po_path, catalog)
            for source, problem in skipped:
                print('  left untranslated ({}): {}'.format(problem, source[:80].replace('\n', ' ')), flush=True)
            with tempfile.TemporaryDirectory() as temporary:
                result = build_english(docs, Path(temporary) / 'html')
            warnings = [line for line in (result.stderr or '').splitlines() if 'WARNING' in line or 'ERROR' in line]
            print('  English build: {}'.format('ok' if result.returncode == 0 else 'FAILED'), flush=True)
            for line in warnings[:30]:
                print('    ' + line, flush=True)
            failed_build = failed_build or result.returncode != 0
    finally:
        if used_model:
            # GPU のメモリを空ける(Maya と取り合わないように)。
            ollama('generate', {'model': args.model, 'keep_alive': 0}, timeout=60)
    return 1 if failed_build else 0


if __name__ == '__main__':
    sys.exit(main())
