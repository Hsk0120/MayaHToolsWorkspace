"""動画を、ローカルのツールだけで文字起こし・画面の文字の読み取り・要約する。

使い方(リポジトリ直下から。faster-whisper を入れた Python で実行する)::

    .maya-output/video-summary/venv/Scripts/python.exe tools/video_summary.py movie.mp4
    ... tools/video_summary.py movie.mp4 --no-frames          # 音声の文字起こしと要約だけ
    ... tools/video_summary.py movie.mp4 --no-audio           # 画面の文字の読み取りと要約だけ
    ... tools/video_summary.py movie.mp4 --language en --max-frames 20
    ... tools/video_summary.py movie.mp4 --start 600 --duration 300   # 10分目から5分だけ(試すとき)
    ... tools/video_summary.py movie.mp4 --no-translate         # 日本語以外の文字起こしを訳さない

流れ:

1. ffmpeg で音声(16kHz・モノラルのwav)と、画面が切り替わったコマの画像を取り出す。
   場面の切り替わりが無くても ``--interval`` 秒ごとに1枚は取り出す。多すぎるときは ``--max-frames`` 枚へ均等に間引く。
2. faster-whisper(既定は ``large-v3``・GPU)で音声をタイムスタンプ付きの文字にする。終わったらモデルを解放する。
3. 音声が日本語以外なら、文字起こしを Ollama で日本語に訳す(``--no-translate`` で省く)。
4. Ollama の画像を読めるモデル(既定は ``gemma3:27b``)で、各コマに映る文字を書き出させる。
5. 文字起こし(原文)と画面の文字を合わせ、同じモデルで日本語の要約を作る。長いときは区切って要約してからまとめる。
6. 最後にモデルを GPU から下ろす(Maya と GPU を取り合わないように)。

結果は ``.maya-output/video-summary/<動画名>_<日時>/`` に保存する(Git対象外)::

    transcript.txt / transcript.srt   音声の文字起こし
    transcript.json                    同じ出力先で再実行するときに使い回す文字起こし
    transcript_ja.txt / transcript_ja.srt  文字起こしの日本語訳(音声が日本語以外のとき)
    screen_text.json                   同じ出力先で再実行するときに使い回す画面の文字
    frames/                            取り出したコマの画像
    screen_text.md                     コマごとの画面の文字
    summary.md                         要約
    run.json                           設定・所要時間など

実行環境の用意(初回のみ)::

    winget install --id Gyan.FFmpeg -e
    py -3.12 -m venv .maya-output/video-summary/venv
    .maya-output/video-summary/venv/Scripts/python.exe -m pip install faster-whisper nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*"
    ollama pull gemma3:27b

GPU のメモリを最大で約20GB使うため、Maya で重い作業をしていないときに実行する(CLAUDE.md の Ollama の決まり)。
動画・音声は外部へ送らない(Ollama は 127.0.0.1 のみ)。
"""
import argparse
import base64
import gc
import glob
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import wave

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / '.maya-output' / 'video-summary'
OLLAMA = 'http://127.0.0.1:11434/api/'
DEFAULT_VISION_MODEL = 'gemma3:27b'
DEFAULT_WHISPER_MODEL = 'large-v3'

#: 1回の要約に渡す文字数の上限。超えたら区切って要約してからまとめる。
CHUNK_CHARS = 12000

OCR_PROMPT = (
    'この画像は動画の1コマです。画面に表示されている文字(ウィンドウの題名・メニュー・ボタン・ラベル・'
    'テロップ・スライドの本文・コードなど)を、見えるとおりに書き出してください。\n'
    '- 推測で補わず、読めない部分は「…」とする。\n'
    '- 読む順(上から下、左から右)に、まとまりごとに改行する。\n'
    '- 最後に「画面の内容:」として、何をしている画面かを1文で書く。\n'
    '- 文字がほとんど無ければ「(文字なし)」と書き、画面の内容だけを書く。'
)

TRANSLATE_PROMPT = (
    '以下は動画の音声を自動で文字起こしした文の一覧です。各行を自然な日本語に訳してください。\n'
    '- 1行ずつ、行頭の [番号] をそのまま付けて、同じ順番・同じ行数で出力する。行をまとめたり分けたりしない。\n'
    '- 文が行をまたいでいても、各行にはその行の部分の訳だけを書く。\n'
    '- 固有名詞・製品名・ツール名・コード・数値は原語のまま残してよい。\n'
    '- 訳文以外(説明・前置き・引用符)は書かない。'
)

#: 1回の翻訳に渡す行数。前後の文脈を保ちつつ、応答が長くなりすぎない量。
TRANSLATE_BATCH = 30

CHUNK_PROMPT = (
    '以下は動画の一部の記録です。[音声] は話した内容の文字起こし、[画面] はその時刻の画面に映った文字です。'
    '文字起こしには聞き間違いが含まれることがあります。\n'
    'この部分で扱われている内容を、日本語の箇条書きで要約してください。'
    '時刻(mm:ss)を各項目の先頭に付け、操作・説明・結果を具体的に書いてください。記録に無いことは書かないでください。'
)

FINAL_PROMPT = (
    '以下は1本の動画の記録(またはその部分ごとの要約)です。動画全体の要約を日本語のMarkdownで作ってください。\n'
    '構成:\n'
    '## 概要\n(3〜5文で、何の動画か・何を示しているか)\n'
    '## 流れ\n(時刻 mm:ss 付きの箇条書き。章や場面の区切りごと)\n'
    '## 要点\n(重要な点・結論・数値を箇条書き)\n'
    '記録に無いことは推測で書かず、不明な点は不明と書いてください。'
)


# ---------------------------------------------------------------------------------------------------------------------
# 共通


def log(message):
    """進み具合を表示する。

    Args:
        message (str): 表示する文。
    """
    line = '[video_summary] ' + message
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        # 端末の文字コード(cp932 など)で表せない文字(フランス語のアクセント記号など)で止まらないようにする。
        # 保存するファイルは UTF-8 なので影響しない。
        encoding = getattr(sys.stdout, 'encoding', None) or 'ascii'
        print(line.encode(encoding, errors='replace').decode(encoding), flush=True)


def timestamp(seconds, srt=False):
    """秒を時刻の文字列にする。

    Args:
        seconds (float): 秒。
        srt (bool): True なら SRT 形式(``HH:MM:SS,mmm``)、False なら ``mm:ss``(1時間以上は ``h:mm:ss``)。

    Returns:
        str: 時刻の文字列。
    """
    if srt:
        milliseconds = int(round(seconds * 1000))
        hours, rest = divmod(milliseconds, 3600000)
        minutes, rest = divmod(rest, 60000)
        secs, milliseconds = divmod(rest, 1000)
        return '{:02d}:{:02d}:{:02d},{:03d}'.format(hours, minutes, secs, milliseconds)
    total = int(seconds)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return '{}:{:02d}:{:02d}'.format(hours, minutes, secs)
    return '{:02d}:{:02d}'.format(minutes, secs)


def find_executable(name):
    """ffmpeg・ffprobe の場所を探す。

    winget で入れた直後は、開いていた端末の PATH に反映されていないことがあるため、
    winget のリンク先と導入先も探す。

    Args:
        name (str): ``ffmpeg`` または ``ffprobe``。

    Returns:
        str: 実行ファイルのパス。

    Raises:
        RuntimeError: 見つからない場合。
    """
    found = shutil.which(name)
    if found:
        return found
    local = os.environ.get('LOCALAPPDATA', '')
    patterns = [
        os.path.join(local, 'Microsoft', 'WinGet', 'Links', name + '.exe'),
        os.path.join(local, 'Microsoft', 'WinGet', 'Packages', 'Gyan.FFmpeg*', '*', 'bin', name + '.exe'),
    ]
    for pattern in patterns:
        matches = sorted(glob.glob(pattern))
        if matches:
            return matches[-1]
    raise RuntimeError('{} was not found. Install it with: winget install --id Gyan.FFmpeg -e'.format(name))


def run(command):
    """外部コマンドを実行し、失敗したら標準エラーの末尾を付けて例外にする。

    Args:
        command (list[str]): コマンドと引数。

    Returns:
        subprocess.CompletedProcess: 実行結果(標準出力・標準エラーは文字列)。

    Raises:
        RuntimeError: 終了コードが0以外の場合。
    """
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if result.returncode != 0:
        raise RuntimeError('Command failed ({}): {}\n{}'.format(result.returncode, ' '.join(command),
                                                                 result.stderr[-2000:]))
    return result


def gpu_status():
    """GPU のメモリの使用状況と、Maya が起動しているかを調べる。

    Returns:
        dict: ``free_mb`` (int または None)・``maya_running`` (bool)。
    """
    status = {'free_mb': None, 'maya_running': False}
    try:
        output = subprocess.run(['nvidia-smi', '--query-gpu=memory.free', '--format=csv,noheader,nounits'],
                                capture_output=True, text=True, timeout=10).stdout
        status['free_mb'] = int(output.split()[0])
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        pass
    if os.name == 'nt':
        try:
            output = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq maya.exe', '/NH'],
                                    capture_output=True, text=True, timeout=10).stdout
            status['maya_running'] = 'maya.exe' in output.lower()
        except (OSError, subprocess.SubprocessError):
            pass
    return status


# ---------------------------------------------------------------------------------------------------------------------
# ffmpeg


def probe(ffprobe, video):
    """動画の長さと、音声があるかを調べる。

    Args:
        ffprobe (str): ffprobe のパス。
        video (Path): 動画。

    Returns:
        dict: ``duration`` (float, 秒)・``has_audio`` (bool)・``width``/``height`` (int)。
    """
    output = run([ffprobe, '-v', 'error', '-print_format', 'json', '-show_format', '-show_streams', str(video)]).stdout
    info = json.loads(output)
    streams = info.get('streams', [])
    video_stream = next((s for s in streams if s.get('codec_type') == 'video'), {})
    return {
        'duration': float(info.get('format', {}).get('duration') or 0.0),
        'has_audio': any(s.get('codec_type') == 'audio' for s in streams),
        'width': int(video_stream.get('width') or 0),
        'height': int(video_stream.get('height') or 0),
    }


def clip_args(start, duration):
    """処理する範囲を ffmpeg の入力の引数にする。

    Args:
        start (float): 開始位置(秒)。0なら先頭から。
        duration (float): 長さ(秒)。0なら最後まで。

    Returns:
        list[str]: ``-i`` の前に置く引数。
    """
    args = []
    if start:
        args += ['-ss', str(start)]
    if duration:
        args += ['-t', str(duration)]
    return args


def extract_audio(ffmpeg, video, destination, clip):
    """音声を Whisper が読む形式(16kHz・モノラルの wav)で書き出す。

    Args:
        ffmpeg (str): ffmpeg のパス。
        video (Path): 動画。
        destination (Path): 書き出す wav。
        clip (list[str]): ``clip_args()`` の引数。
    """
    run([ffmpeg, '-y', '-v', 'error'] + clip + ['-i', str(video), '-map', '0:a:0', '-vn', '-ac', '1', '-ar', '16000',
                                               '-c:a', 'pcm_s16le', str(destination)])


def extract_frames(ffmpeg, video, directory, threshold, interval, max_frames, width, clip):
    """画面が切り替わったコマと、一定間隔のコマを画像で書き出す。

    ffmpeg の ``select`` で、場面の変化量が ``threshold`` を超えたコマ・最初のコマ・前に選んだコマから
    ``interval`` 秒以上たったコマを選ぶ。各コマの時刻は ``showinfo`` の出力から読む。

    Args:
        ffmpeg (str): ffmpeg のパス。
        video (Path): 動画。
        directory (Path): 画像を置くフォルダー。
        threshold (float): 場面の切り替わりとみなす変化量(0〜1)。
        interval (float): 切り替わりが無くても取り出す間隔(秒)。
        max_frames (int): 残す枚数の上限。超えた分は均等に間引く。
        width (int): 画像の幅(px)。元より大きくはしない。
        clip (list[str]): ``clip_args()`` の引数。時刻は範囲の先頭からの秒になる。

    Returns:
        list[dict]: ``path`` (Path)・``time`` (float, 秒) の一覧(時刻順)。
    """
    directory.mkdir(parents=True, exist_ok=True)
    expression = "gt(scene,{})+isnan(prev_selected_t)+gte(t-prev_selected_t,{})".format(threshold, interval)
    filters = "select='{}',showinfo,scale='min({},iw)':-2".format(expression, width)
    pattern = str(directory / 'frame_%04d.png')
    # 埋め込みのカバー画像(mjpeg の映像トラック)を読まないよう、最初の映像トラックを指定する。
    result = run([ffmpeg, '-y', '-hide_banner'] + clip + ['-i', str(video), '-map', '0:v:0', '-vf', filters,
                                                          '-fps_mode', 'vfr', pattern])
    times = [float(value) for value in re.findall(r'pts_time:\s*([0-9.]+)', result.stderr)]
    paths = sorted(directory.glob('frame_*.png'))
    frames = [{'path': path, 'time': times[index] if index < len(times) else 0.0} for index, path in enumerate(paths)]
    if len(frames) > max_frames:
        step = len(frames) / float(max_frames)
        keep = {int(index * step) for index in range(max_frames)}
        for index, frame in enumerate(frames):
            if index not in keep:
                frame['path'].unlink()
        frames = [frame for index, frame in enumerate(frames) if index in keep]
    return frames


# ---------------------------------------------------------------------------------------------------------------------
# faster-whisper


def add_cuda_dll_directories():
    """pip で入れた CUDA のライブラリ(cuBLAS・cuDNN)を読めるようにする。

    ctranslate2 は DLL を名前で探すため、``site-packages/nvidia/*/bin`` を PATH と DLL の検索先に加える。
    faster_whisper を import する前に呼ぶ。
    """
    for site in sys.path:
        for directory in glob.glob(os.path.join(site, 'nvidia', '*', 'bin')):
            os.environ['PATH'] = directory + os.pathsep + os.environ.get('PATH', '')
            if hasattr(os, 'add_dll_directory'):
                os.add_dll_directory(directory)


def transcribe(audio, model_name, language, device):
    """音声を文字にする。

    Args:
        audio (Path): 16kHz・モノラルの wav。
        model_name (str): Whisper のモデル名(``large-v3``・``medium`` など)。初回はダウンロードされる。
        language (str): 言語コード(``ja`` など)。``auto`` なら自動判定。
        device (str): ``cuda`` または ``cpu``。

    Returns:
        tuple[list[dict], dict]: 区間の一覧(``start``・``end``・``text``)と、判定した言語などの情報。
    """
    add_cuda_dll_directories()
    # Windows ではシンボリックリンクを作れないことが多く、モデル取得のたびに警告が出るため止める(動作は同じ)。
    os.environ.setdefault('HF_HUB_DISABLE_SYMLINKS_WARNING', '1')
    import numpy
    from faster_whisper import WhisperModel

    # faster-whisper の音声の読み込み(PyAV)は版の組み合わせで失敗することがあるため、
    # 自分で書き出した 16kHz・モノラル・16bit の wav を直接読んで配列で渡す。
    with wave.open(str(audio), 'rb') as reader:
        samples = numpy.frombuffer(reader.readframes(reader.getnframes()), dtype=numpy.int16)
    samples = samples.astype(numpy.float32) / 32768.0

    compute_type = 'float16' if device == 'cuda' else 'int8'
    model = WhisperModel(model_name, device=device, compute_type=compute_type)
    try:
        # 無音区間で同じ文を繰り返す誤認識を減らすため、VAD(声のある区間の検出)を使う。
        segments, info = model.transcribe(samples, language=None if language == 'auto' else language,
                                          vad_filter=True, beam_size=5, condition_on_previous_text=False)
        result = []
        for segment in segments:
            text = segment.text.strip()
            if text:
                result.append({'start': segment.start, 'end': segment.end, 'text': text})
                log('  {} {}'.format(timestamp(segment.start), text))
        return result, {'language': info.language, 'language_probability': info.language_probability}
    finally:
        # 次の工程で Ollama が GPU を使えるよう、Whisper のモデルを解放する。
        del model
        gc.collect()


def write_transcript(segments, directory, stem='transcript'):
    """文字起こしを txt と srt で保存する。

    Args:
        segments (list[dict]): ``transcribe()`` の区間の一覧。
        directory (Path): 保存先のフォルダー。
        stem (str): ファイル名(拡張子なし)。
    """
    lines = ['[{}] {}'.format(timestamp(segment['start']), segment['text']) for segment in segments]
    (directory / (stem + '.txt')).write_text('\n'.join(lines) + '\n', encoding='utf-8')
    blocks = []
    for index, segment in enumerate(segments, 1):
        blocks.append('{}\n{} --> {}\n{}\n'.format(index, timestamp(segment['start'], srt=True),
                                                   timestamp(segment['end'], srt=True), segment['text']))
    (directory / (stem + '.srt')).write_text('\n'.join(blocks), encoding='utf-8')


# ---------------------------------------------------------------------------------------------------------------------
# Ollama


def ollama(path, payload, timeout=900):
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
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        # 500 などの理由は本文に入っているので、例外の文に付ける。
        detail = error.read().decode('utf-8', errors='replace')[:500]
        raise RuntimeError('Ollama {} failed: HTTP {} {}'.format(path, error.code, detail)) from error


def ensure_ollama(model):
    """Ollama のサーバーが動いていて、モデルが入っていることを確かめる。

    サーバーが動いていなければ ``ollama serve`` を起動して待つ(CLAUDE.md で許可された範囲)。

    Args:
        model (str): 使うモデル名。

    Raises:
        RuntimeError: サーバーが起動しない、またはモデルが入っていない場合。
    """
    try:
        urllib.request.urlopen(OLLAMA + 'version', timeout=5)
    except (urllib.error.URLError, OSError):
        log('Starting the Ollama server...')
        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        subprocess.Popen(['ollama', 'serve'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
        for _ in range(60):
            time.sleep(1)
            try:
                urllib.request.urlopen(OLLAMA + 'version', timeout=5)
                break
            except (urllib.error.URLError, OSError):
                continue
        else:
            raise RuntimeError('The Ollama server did not start.')
    with urllib.request.urlopen(OLLAMA + 'tags', timeout=10) as response:
        names = {item['name'] for item in json.load(response).get('models', [])}
    if model not in names and model + ':latest' not in names:
        raise RuntimeError('Ollama model "{}" is not installed. Run: ollama pull {}'.format(model, model))


def chat(model, prompt, text=None, image=None, num_predict=2048):
    """Ollama のモデルに1回質問する。

    Args:
        model (str): モデル名。
        prompt (str): 指示。
        text (str): 指示の後に付ける本文。
        image (Path): 一緒に渡す画像。
        num_predict (int): 応答の長さの上限(トークン数)。

    Returns:
        str: 応答の本文。
    """
    content = prompt if text is None else prompt + '\n\n---\n' + text
    message = {'role': 'user', 'content': content}
    if image is not None:
        message['images'] = [base64.b64encode(image.read_bytes()).decode('ascii')]
    # 同じ入力で同じ結果になるよう temperature を低くし、長い反復生成で GPU を占有しないよう長さを制限する。
    options = {'temperature': 0.2, 'seed': 42, 'num_ctx': 16384, 'num_predict': num_predict}
    try:
        reply = ollama('chat', {'model': model, 'messages': [message], 'stream': False, 'keep_alive': '10m',
                                'options': options})
    except RuntimeError as error:
        if 'repeat' not in str(error):
            raise
        # 同じ語句を繰り返して打ち切られた(token repeat limit)ときは、揺らぎを少し増やし、
        # 繰り返しを抑える設定で1回だけ言い直させる。
        log('  Retrying after a repetition stop.')
        options.update({'temperature': 0.6, 'seed': 43, 'repeat_penalty': 1.15})
        reply = ollama('chat', {'model': model, 'messages': [message], 'stream': False, 'keep_alive': '10m',
                                'options': options})
    return reply['message']['content'].strip()


def read_frames(model, frames, directory):
    """各コマに映る文字を読み取り、Markdown に保存する。

    Args:
        model (str): 画像を読めるモデル名。
        frames (list[dict]): ``extract_frames()`` の一覧。
        directory (Path): 保存先のフォルダー。

    Returns:
        list[dict]: ``time``・``image`` (ファイル名)・``text`` の一覧。
    """
    results = []
    lines = ['# Screen text', '']
    for index, frame in enumerate(frames, 1):
        log('  frame {}/{} ({})'.format(index, len(frames), timestamp(frame['time'])))
        text = None
        # Ollama が1コマだけ失敗することがあるため、1回だけ言い直させ、それでも駄目なら記録して次へ進む。
        for attempt in range(2):
            try:
                text = chat(model, OCR_PROMPT, image=frame['path'], num_predict=1024)
                break
            except (RuntimeError, urllib.error.URLError, OSError) as error:
                log('  Warning: frame {} failed (attempt {}): {}'.format(frame['path'].name, attempt + 1, error))
        if text is None:
            text = '(読み取り失敗)'
        results.append({'time': frame['time'], 'image': frame['path'].name, 'text': text})
        lines += ['## {} `{}`'.format(timestamp(frame['time']), frame['path'].name), '', text, '']
    (directory / 'screen_text.md').write_text('\n'.join(lines), encoding='utf-8')
    (directory / 'screen_text.json').write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding='utf-8')
    return results


def translate_segments(model, segments):
    """文字起こしの各区間を日本語に訳す。時刻はそのまま残す。

    ``TRANSLATE_BATCH`` 行ずつまとめて訳させ、前後の文脈を保つ。応答の行数や番号が合わないまとまりは、
    1行ずつ訳し直す(1行でも失敗したら原文のまま残す)。

    Args:
        model (str): Ollama のモデル名。
        segments (list[dict]): ``transcribe()`` の区間の一覧。

    Returns:
        list[dict]: ``start``・``end``・``text`` (訳文) の一覧。
    """
    translated = []
    for first in range(0, len(segments), TRANSLATE_BATCH):
        batch = segments[first:first + TRANSLATE_BATCH]
        log('  lines {}-{}/{}'.format(first + 1, first + len(batch), len(segments)))
        source = '\n'.join('[{}] {}'.format(index, segment['text']) for index, segment in enumerate(batch, 1))
        texts = None
        try:
            reply = chat(model, TRANSLATE_PROMPT, source, num_predict=4096)
            found = dict(re.findall(r'^\s*\[(\d+)\]\s*(.*\S)\s*$', reply, flags=re.MULTILINE))
            if len(found) == len(batch) and all(str(index) in found for index in range(1, len(batch) + 1)):
                texts = [found[str(index)] for index in range(1, len(batch) + 1)]
        except (RuntimeError, urllib.error.URLError, OSError) as error:
            log('  Warning: batch failed: {}'.format(error))
        if texts is None:
            log('  Line count mismatch. Translating line by line.')
            texts = []
            for segment in batch:
                try:
                    reply = chat(model, TRANSLATE_PROMPT, '[1] ' + segment['text'], num_predict=512)
                    match = re.search(r'\[1\]\s*(.*\S)', reply)
                    texts.append(match.group(1) if match else reply.strip() or segment['text'])
                except (RuntimeError, urllib.error.URLError, OSError) as error:
                    log('  Warning: line failed, keeping the original: {}'.format(error))
                    texts.append(segment['text'])
        translated += [dict(segment, text=text) for segment, text in zip(batch, texts)]
    return translated


def build_record(segments, screens):
    """文字起こしと画面の文字を、時刻順に1つの記録にまとめる。

    Args:
        segments (list[dict]): 音声の区間の一覧。
        screens (list[dict]): ``read_frames()`` の一覧。

    Returns:
        list[str]: 時刻順の行(1行=1項目)。
    """
    items = [(segment['start'], '[{}][音声] {}'.format(timestamp(segment['start']), segment['text']))
             for segment in segments]
    for screen in screens:
        text = re.sub(r'\s*\n\s*', ' / ', screen['text'])
        items.append((screen['time'], '[{}][画面] {}'.format(timestamp(screen['time']), text)))
    items.sort(key=lambda item: item[0])
    return [line for _, line in items]


def summarize(model, record, title):
    """記録を要約する。長いときは区切って要約してから、まとめの要約を作る。

    Args:
        model (str): モデル名。
        record (list[str]): ``build_record()`` の行。
        title (str): 動画のファイル名(要約の手がかりに渡す)。

    Returns:
        str: Markdown の要約。
    """
    chunks, current = [], []
    for line in record:
        if current and sum(len(item) for item in current) + len(line) > CHUNK_CHARS:
            chunks.append(current)
            current = []
        current.append(line)
    if current:
        chunks.append(current)
    header = 'ファイル名: {}\n'.format(title)
    if len(chunks) <= 1:
        return chat(model, FINAL_PROMPT, header + '\n'.join(record), num_predict=3072)
    partials = []
    for index, chunk in enumerate(chunks, 1):
        log('  chunk {}/{}'.format(index, len(chunks)))
        partials.append(chat(model, CHUNK_PROMPT, '\n'.join(chunk)))
    log('  combining')
    return chat(model, FINAL_PROMPT, header + '\n\n'.join(partials), num_predict=3072)


# ---------------------------------------------------------------------------------------------------------------------


def parse_args(argv=None):
    """コマンドラインの引数を読む。

    Args:
        argv (list[str]): 引数。None なら ``sys.argv``。

    Returns:
        argparse.Namespace: 読んだ引数。
    """
    parser = argparse.ArgumentParser(description='Transcribe, read on-screen text and summarize a video locally.')
    parser.add_argument('video', type=Path, help='Video file to process.')
    parser.add_argument('--output', type=Path, help='Output folder (default: .maya-output/video-summary/<name>_<time>).')
    parser.add_argument('--language', default='auto', help='Speech language code such as ja or en, or "auto" (default: auto).')
    parser.add_argument('--whisper-model', default=DEFAULT_WHISPER_MODEL, help='faster-whisper model (default: large-v3).')
    parser.add_argument('--device', default='cuda', choices=['cuda', 'cpu'], help='Device for Whisper (default: cuda).')
    parser.add_argument('--model', default=DEFAULT_VISION_MODEL, help='Ollama vision model (default: gemma3:27b).')
    parser.add_argument('--threshold', type=float, default=0.1, help='Scene change threshold 0-1 (default: 0.1).')
    parser.add_argument('--interval', type=float, default=10.0, help='Max seconds between frames (default: 10).')
    parser.add_argument('--max-frames', type=int, default=40, help='Max frames to read (default: 40).')
    parser.add_argument('--frame-width', type=int, default=1280, help='Frame width in pixels (default: 1280).')
    parser.add_argument('--start', type=float, default=0.0, help='Start position in seconds (default: 0).')
    parser.add_argument('--duration', type=float, default=0.0, help='Length in seconds; 0 means to the end.')
    parser.add_argument('--no-audio', action='store_true', help='Skip speech transcription.')
    parser.add_argument('--no-frames', action='store_true', help='Skip on-screen text reading.')
    parser.add_argument('--no-summary', action='store_true', help='Skip the summary.')
    parser.add_argument('--no-translate', action='store_true',
                        help='Do not translate a non-Japanese transcript into Japanese.')
    return parser.parse_args(argv)


def main(argv=None):
    """動画を処理して結果を保存する。

    Args:
        argv (list[str]): 引数。None なら ``sys.argv``。

    Returns:
        int: 終了コード(成功は0)。
    """
    args = parse_args(argv)
    video = args.video.resolve()
    if not video.is_file():
        log('Video not found: {}'.format(video))
        return 2
    ffmpeg, ffprobe = find_executable('ffmpeg'), find_executable('ffprobe')
    directory = args.output or OUTPUT_ROOT / '{}_{}'.format(video.stem, time.strftime('%Y%m%d_%H%M%S'))
    directory.mkdir(parents=True, exist_ok=True)

    status = gpu_status()
    if status['maya_running']:
        log('Warning: Maya is running. This uses up to about 20 GB of GPU memory '
            '(free now: {} MB).'.format(status['free_mb']))

    info = probe(ffprobe, video)
    log('Video: {} ({}, {}x{}, audio: {})'.format(video.name, timestamp(info['duration']), info['width'],
                                                   info['height'], 'yes' if info['has_audio'] else 'no'))
    report = {'video': str(video), 'output': str(directory), 'probe': info, 'args': {
        key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()}, 'seconds': {}}

    clip = clip_args(args.start, args.duration)
    # 範囲を指定したときは、結果の時刻を動画の先頭からの時刻に直す。
    offset = args.start

    use_model = not (args.no_frames and args.no_summary and args.no_translate)
    if use_model:
        ensure_ollama(args.model)

    segments = []
    cached = directory / 'transcript.json'
    if not args.no_audio and info['has_audio'] and cached.is_file():
        # 同じ出力先でやり直すときは、時間のかかる文字起こしを使い回す。
        data = json.loads(cached.read_text(encoding='utf-8'))
        # 以前の形式(区間の一覧だけ)も読めるようにする。
        segments, speech = (data, {}) if isinstance(data, list) else (data['segments'], data.get('speech', {}))
        report['speech'] = dict(speech, segments=len(segments))
        log('Reusing {} ({} segments).'.format(cached.name, len(segments)))
    elif not args.no_audio and info['has_audio']:
        started = time.time()
        log('Extracting audio...')
        audio = directory / 'audio.wav'
        extract_audio(ffmpeg, video, audio, clip)
        log('Transcribing with faster-whisper ({}, {})...'.format(args.whisper_model, args.device))
        segments, speech = transcribe(audio, args.whisper_model, args.language, args.device)
        for segment in segments:
            segment['start'] += offset
            segment['end'] += offset
        write_transcript(segments, directory)
        cached.write_text(json.dumps({'speech': speech, 'segments': segments}, ensure_ascii=False, indent=1),
                          encoding='utf-8')
        audio.unlink()
        report['speech'] = dict(speech, segments=len(segments))
        report['seconds']['transcribe'] = round(time.time() - started, 1)
    elif not args.no_audio:
        log('The video has no audio track. Skipping transcription.')

    screens = []
    try:
        language = report.get('speech', {}).get('language')
        if segments and not args.no_translate and language and language != 'ja':
            started = time.time()
            translated_cache = directory / 'transcript_ja.json'
            if translated_cache.is_file():
                translated = json.loads(translated_cache.read_text(encoding='utf-8'))
                log('Reusing {} ({} lines).'.format(translated_cache.name, len(translated)))
            else:
                log('Translating the transcript ({}) into Japanese with {}...'.format(language, args.model))
                translated = translate_segments(args.model, segments)
                translated_cache.write_text(json.dumps(translated, ensure_ascii=False, indent=1), encoding='utf-8')
            write_transcript(translated, directory, 'transcript_ja')
            report['seconds']['translate'] = round(time.time() - started, 1)
        elif segments and not args.no_translate and not language:
            log('The speech language is unknown. Skipping translation.')

        screens_cache = directory / 'screen_text.json'
        if not args.no_frames and screens_cache.is_file():
            # 同じ出力先でやり直すときは、時間のかかる画面の読み取りを使い回す。
            screens = json.loads(screens_cache.read_text(encoding='utf-8'))
            report['frames'] = len(screens)
            log('Reusing {} ({} frames).'.format(screens_cache.name, len(screens)))
        elif not args.no_frames:
            started = time.time()
            log('Extracting frames...')
            frames = extract_frames(ffmpeg, video, directory / 'frames', args.threshold, args.interval,
                                    args.max_frames, args.frame_width, clip)
            for frame in frames:
                frame['time'] += offset
            log('Reading on-screen text from {} frames with {}...'.format(len(frames), args.model))
            screens = read_frames(args.model, frames, directory)
            report['frames'] = len(frames)
            report['seconds']['frames'] = round(time.time() - started, 1)

        record = build_record(segments, screens)
        (directory / 'record.txt').write_text('\n'.join(record) + '\n', encoding='utf-8')
        if not args.no_summary:
            if not record:
                log('Nothing to summarize (no speech and no frames).')
            else:
                started = time.time()
                log('Summarizing with {}...'.format(args.model))
                summary = summarize(args.model, record, video.name)
                (directory / 'summary.md').write_text('# {}\n\n{}\n'.format(video.name, summary), encoding='utf-8')
                report['seconds']['summary'] = round(time.time() - started, 1)
    finally:
        if use_model:
            # GPU のメモリを空ける(Maya と取り合わないように)。
            try:
                ollama('generate', {'model': args.model, 'keep_alive': 0}, timeout=60)
            except (urllib.error.URLError, OSError):
                pass
        (directory / 'run.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    log('Done: {}'.format(directory))
    return 0


if __name__ == '__main__':
    sys.exit(main())
