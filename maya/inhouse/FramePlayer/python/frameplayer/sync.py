"""FramePlayerとMayaのタイムスライダーを双方向に連携させる接続。

FramePlayerは連携モード(下段の「Maya連携」ボタン、または起動時の ``--sync``)のときだけ、
このPCの中だけで接続できる待ち受け口(既定は7010番)を開く。通常モードではポートを開かない。
この接続はそこへつなぎ、1行1命令の文字で次のものをやり取りする。

- Maya → FramePlayer: ``frame <番号>``、``range <最初> <最後>``、``play``、``stop``、``hello maya``
- FramePlayer → Maya: ``frame <番号>``、``range <最初> <最後>``、``state playing|stopped``、
  ``hello FramePlayer 1``

つないだ直後に、互いが同じ鍵を持つ相手かを確かめる(相互認証)。鍵はユーザーごとの
``%LOCALAPPDATA%\\FramePlayer\\sync.key`` (FramePlayerが初回の起動時に作る)で、通信には流さない。

1. FramePlayer → Maya: ``challenge <乱数>``
2. Maya → FramePlayer: ``auth <HMAC-SHA256(鍵, "maya-to-player:" + 1の乱数)> <Mayaの乱数>``
3. FramePlayer → Maya: ``auth <HMAC-SHA256(鍵, "player-to-maya:" + Mayaの乱数)>``

3が正しくなければ、相手はFramePlayerではない(同じ番号を別のプログラムが開いている)ので、すぐに切る。
同じPCの他のユーザーのプロセスや、ブラウザのページは鍵を読めないので、FramePlayerを操作できない。

フレーム番号の対応は Keyframe Pro と同じ考え方で、
``FramePlayerの番号 = round(Mayaの番号 * multiplier) + offset`` とする。

受け取った命令でMayaを動かしている間は、その変化を送り返さない(行ったり来たりを防ぐ)。
FramePlayerの再生中は1コマごとに番号が届くが、Mayaへは最後に届いた番号だけを反映する
(重いシーンでも遅れが積み重ならないように)。

Mayaのコマンドはメインスレッドでしか呼べないため、受信用のスレッドで受け取った命令は
``maya.utils.executeDeferred`` でメインスレッドへ渡して実行する。

このモジュールは maya.cmds・maya.api.OpenMaya・標準ライブラリだけを使い、他の社内ライブラリに依存しない。
"""

import binascii
import hashlib
import hmac
import os
import secrets
import socket
import threading

import maya.api.OpenMaya as om
import maya.cmds as cmds
import maya.utils

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7010
MAX_FRAME = 100000000           # 受け付けるフレーム番号の絶対値の上限(FramePlayerと同じ)。
MAX_LINE_BYTES = 4096           # 1行の長さの上限。改行の来ない長すぎる文字を送ってくる相手は切る。
AUTH_TIMEOUT = 3.0              # 認証のやり取りを待つ秒数。


def key_path():
    """連携の鍵ファイルのパスを返す。

    Returns:
        str: ``%LOCALAPPDATA%\\FramePlayer\\sync.key``。
    """
    return os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "FramePlayer", "sync.key")


def load_key():
    """連携の鍵を読む。

    Returns:
        str or None: 鍵(16進数64文字)。ファイルが無い・壊れている場合はNone(FramePlayerを一度起動すると作られる)。
    """
    try:
        with open(key_path(), "r", encoding="ascii") as stream:
            key = stream.read().strip()
    except (OSError, UnicodeDecodeError):
        return None
    if len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
        return None
    return key


def _mac(key, message):
    """HMAC-SHA256を16進数で返す。

    Args:
        key (str): 鍵。
        message (str): 対象の文字列。

    Returns:
        str: 16進数64文字。
    """
    return hmac.new(key.encode("ascii"), message.encode("ascii"), hashlib.sha256).hexdigest()


def _is_hex(text, min_length, max_length):
    """小文字の16進数で、長さが範囲内かを返す。

    Args:
        text (str): 調べる文字列。
        min_length (int): 最短の長さ。
        max_length (int): 最長の長さ。

    Returns:
        bool: 条件に合えばTrue。
    """
    return min_length <= len(text) <= max_length and all(c in "0123456789abcdef" for c in text)


def _to_frame(text):
    """フレーム番号の文字列を整数にする(範囲外・数でなければNone)。

    Args:
        text (str): 文字列。

    Returns:
        int or None: フレーム番号。
    """
    if len(text) > 12:
        return None
    try:
        value = int(text)
    except ValueError:
        return None
    return value if -MAX_FRAME <= value <= MAX_FRAME else None


class FramePlayerSync(object):
    """FramePlayerとの1本の接続と、Mayaの時間の変化を受け取る仕組み(コールバック)をまとめて持つ。

    Args:
        host (str): FramePlayerの待ち受け口のアドレス。
        port (int): FramePlayerの待ち受け口の番号。
        offset (int): フレーム番号のオフセット(FramePlayerの番号 - Mayaの番号)。
        multiplier (float): フレーム番号の倍率(FramePlayerの番号 = Mayaの番号 * multiplier + offset)。
        sync_range (bool): 再生範囲も合わせるか。
        maya_to_player (bool): Mayaの時間の変化をFramePlayerへ送るか。
        player_to_maya (bool): FramePlayerの時間の変化をMayaへ反映するか。
        on_status (callable): 接続状態やFramePlayerの再生状態が変わったときに呼ぶ関数(引数なし)。
            メインスレッドから呼ぶ。
    """

    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT, offset=0, multiplier=1.0, sync_range=True,
                 maya_to_player=True, player_to_maya=True, on_status=None):
        self.host = host
        self.port = int(port)
        self.offset = int(offset)
        self.multiplier = float(multiplier) if multiplier else 1.0
        self.sync_range = bool(sync_range)
        self.maya_to_player = bool(maya_to_player)
        self.player_to_maya = bool(player_to_maya)
        self.on_status = on_status
        self.player_playing = False
        self.last_error = ""     # 最後に接続できなかった理由(画面の警告に使う)。

        self._socket = None
        self._reader = None
        self._callbacks = []
        self._lock = threading.Lock()
        self._pending_frame = None   # FramePlayerから届いた最後のフレーム(まだMayaへ反映していない)。
        self._pending_range = None   # 同じく再生範囲。
        self._scheduled = False      # メインスレッドでの反映を予約済みか。
        self._applying = False       # FramePlayerから受け取った変化をMayaへ反映中か(反映中の変化は送り返さない)。
        self._last_sent_frame = None
        self._last_sent_range = None

    # ------------------------------------------------------------------
    # 接続
    # ------------------------------------------------------------------
    @property
    def connected(self):
        """bool: FramePlayerとつながっているか。"""
        return self._socket is not None

    def connect(self, timeout=2.0):
        """FramePlayerへ接続し、Mayaの時間の変化を受け取り始める。

        Args:
            timeout (float): 接続を待つ秒数。

        Returns:
            bool: 接続できた場合True。FramePlayerが起動していないなどで接続できなければFalse。
        """
        if self.connected:
            return True
        key = load_key()
        if key is None:
            self.last_error = "The sync key was not found. Start FramePlayer once (%s)." % key_path()
            return False
        try:
            sock = socket.create_connection((self.host, self.port), timeout=timeout)
        except OSError:
            self.last_error = ("Cannot connect to FramePlayer. Start FramePlayer and click the 'Maya Sync' button "
                               "at the bottom to enter sync mode (port %d)." % self.port)
            return False
        try:
            leftover = self._authenticate(sock, key)
        except (OSError, ValueError) as error:
            sock.close()
            self.last_error = "Could not verify that the peer is FramePlayer (%s)." % error
            return False
        self.last_error = ""
        self._attach(sock, leftover)
        return True

    @staticmethod
    def _authenticate(sock, key):
        """相手と互いに同じ鍵を持つかを確かめる(相互認証)。

        Args:
            sock (socket.socket): FramePlayerへつながったソケット。
            key (str): 鍵。

        Returns:
            bytes: 認証の後に続けて届いていた文字(命令として後で処理する)。

        Raises:
            ValueError: 相手の応答が正しくない場合(FramePlayerではない、鍵が違う)。
            OSError: 通信に失敗した、時間内に応答が無い場合。
        """
        sock.settimeout(AUTH_TIMEOUT)
        buffer = b""

        def read_line():
            nonlocal buffer
            while b"\n" not in buffer:
                if len(buffer) > 512:
                    raise ValueError("The response is too long")
                data = sock.recv(512)
                if not data:
                    raise ValueError("The peer closed the connection")
                buffer += data
            line, buffer = buffer.split(b"\n", 1)
            return line.decode("ascii", "replace").strip().split()

        challenge = read_line()
        if len(challenge) != 2 or challenge[0] != "challenge" or not _is_hex(challenge[1], 32, 64):
            raise ValueError("No challenge was received")
        nonce = secrets.token_hex(16)
        sock.sendall(("auth %s %s\n" % (_mac(key, "maya-to-player:" + challenge[1]), nonce)).encode("ascii"))
        reply = read_line()
        expected = _mac(key, "player-to-maya:" + nonce)
        if len(reply) != 2 or reply[0] != "auth" or not hmac.compare_digest(reply[1], expected):
            raise ValueError("Invalid response")
        return buffer

    def disconnect(self):
        """接続を切り、Mayaの時間の変化の受け取りもやめる。"""
        sock = self._socket
        self._socket = None
        self._remove_callbacks()
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()
        self.player_playing = False
        self._notify_status()

    def _attach(self, sock, leftover=b""):
        """認証済みのソケットを使い始める(メインスレッドから呼ぶ)。

        Args:
            sock (socket.socket): FramePlayerへつながったソケット。
            leftover (bytes): 認証の後に続けて届いていた文字。
        """
        sock.settimeout(None)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._socket = sock
        self._last_sent_frame = None
        self._last_sent_range = None
        self._reader = threading.Thread(target=self._read_loop, args=(sock, leftover), name="FramePlayerSync")
        self._reader.daemon = True
        self._reader.start()
        self._add_callbacks()
        # つながったら、Mayaの状態をFramePlayerへ合わせる(Maya側を正とする)。
        self._send("hello maya")
        if self.sync_range and self.maya_to_player:
            self._send_range()
        if self.maya_to_player:
            self._send_frame(cmds.currentTime(query=True))
        self._notify_status()

    # ------------------------------------------------------------------
    # 番号の対応
    # ------------------------------------------------------------------
    def to_player(self, maya_frame):
        """Mayaのフレーム番号をFramePlayerの番号にする。

        Args:
            maya_frame (float): Mayaのフレーム番号。

        Returns:
            int: FramePlayerのフレーム番号。
        """
        return int(round(maya_frame * self.multiplier)) + self.offset

    def to_maya(self, player_frame):
        """FramePlayerのフレーム番号をMayaの番号にする。

        Args:
            player_frame (int): FramePlayerのフレーム番号。

        Returns:
            float: Mayaのフレーム番号。倍率が1なら整数の値。
        """
        value = (player_frame - self.offset) / self.multiplier
        return float(round(value)) if self.multiplier == 1.0 else value

    # ------------------------------------------------------------------
    # FramePlayerへの操作
    # ------------------------------------------------------------------
    def play(self):
        """FramePlayerで再生を始める(Mayaは届くフレームに追従する)。"""
        self._send("play")

    def stop(self):
        """FramePlayerの再生を止める。"""
        self._send("stop")

    def push_state(self):
        """今のMayaのフレームと再生範囲を、FramePlayerへ送り直す。"""
        self._last_sent_frame = None
        self._last_sent_range = None
        if self.sync_range:
            self._send_range()
        self._send_frame(cmds.currentTime(query=True))

    def _send(self, line):
        """1行の命令を送る。送れなければ接続を切る。

        Args:
            line (str): 命令(改行は付けない)。
        """
        sock = self._socket
        if sock is None:
            return
        try:
            sock.sendall((line + "\n").encode("utf-8"))
        except OSError:
            maya.utils.executeDeferred(self._connection_lost, sock)

    def _send_frame(self, maya_frame):
        """Mayaのフレームを、FramePlayerの番号にして送る(前回と同じなら送らない)。

        Args:
            maya_frame (float): Mayaのフレーム番号。
        """
        frame = self.to_player(maya_frame)
        if frame == self._last_sent_frame:
            return
        self._last_sent_frame = frame
        self._send("frame %d" % frame)

    def _send_range(self):
        """Mayaの再生範囲を、FramePlayerの番号にして送る(前回と同じなら送らない)。"""
        first = self.to_player(cmds.playbackOptions(query=True, minTime=True))
        last = self.to_player(cmds.playbackOptions(query=True, maxTime=True))
        if (first, last) == self._last_sent_range:
            return
        self._last_sent_range = (first, last)
        self._send("range %d %d" % (first, last))

    # ------------------------------------------------------------------
    # Mayaの変化の受け取り
    # ------------------------------------------------------------------
    def _add_callbacks(self):
        """Mayaの時間・再生範囲の変化を受け取る仕組みを登録する。"""
        self._remove_callbacks()
        self._callbacks.append(om.MDGMessage.addTimeChangeCallback(self._on_time_changed))
        self._callbacks.append(om.MEventMessage.addEventCallback("playbackRangeChanged", self._on_range_changed))

    def _remove_callbacks(self):
        """登録した仕組みを外す。"""
        for callback in self._callbacks:
            try:
                om.MMessage.removeCallback(callback)
            except RuntimeError:
                pass
        self._callbacks = []

    def _on_time_changed(self, time, client_data=None):
        """Mayaの時間が変わったとき(スクラブ・再生・キー操作)に呼ばれる。

        Args:
            time (om.MTime): 新しい時間。
            client_data: 未使用。
        """
        if self._applying or not self.maya_to_player:
            return
        self._send_frame(time.asUnits(om.MTime.uiUnit()))

    def _on_range_changed(self, client_data=None):
        """Mayaの再生範囲が変わったときに呼ばれる。

        Args:
            client_data: 未使用。
        """
        if self._applying or not (self.sync_range and self.maya_to_player):
            return
        self._send_range()

    # ------------------------------------------------------------------
    # FramePlayerからの受け取り(受信用のスレッド)
    # ------------------------------------------------------------------
    def _read_loop(self, sock, buffer=b""):
        """届いた文字を行に分け、命令ごとに処理する(受信用のスレッドで動く)。

        Args:
            sock (socket.socket): 受け取るソケット。
            buffer (bytes): 認証の後に続けて届いていた文字。
        """
        while True:
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                if len(line) <= MAX_LINE_BYTES:
                    self._handle_line(line.decode("utf-8", "replace").strip())
            if len(buffer) > MAX_LINE_BYTES:
                data = b""  # 改行の来ない長すぎる文字は、壊れた相手として切る(メモリを使い切らないように)。
            else:
                try:
                    data = sock.recv(4096)
                except OSError:
                    data = b""
            if not data:
                maya.utils.executeDeferred(self._connection_lost, sock)
                return
            buffer += data

    def _handle_line(self, line):
        """1行の命令を処理する。Mayaへの反映はメインスレッドへ予約する。

        Args:
            line (str): 命令。
        """
        # 決まった命令と、決まった数の値だけを受け付ける(範囲外の番号・余分な語は無視する)。
        parts = line.split()
        if not parts:
            return
        command = parts[0]
        if command == "frame" and len(parts) == 2:
            frame = _to_frame(parts[1])
            if frame is None:
                return
            with self._lock:
                self._pending_frame = frame
        elif command == "range" and len(parts) == 3:
            first, last = _to_frame(parts[1]), _to_frame(parts[2])
            if first is None or last is None:
                return
            with self._lock:
                self._pending_range = (min(first, last), max(first, last))
        elif command == "state" and len(parts) == 2 and parts[1] in ("playing", "stopped"):
            self.player_playing = parts[1] == "playing"
            maya.utils.executeDeferred(self._notify_status)
            return
        else:
            return
        with self._lock:
            if self._scheduled:
                return  # 予約済みの反映が、最新の値をまとめて反映する。
            self._scheduled = True
        maya.utils.executeDeferred(self._apply_pending)

    def _apply_pending(self):
        """FramePlayerから届いた最新のフレームと再生範囲をMayaへ反映する(メインスレッドで動く)。"""
        with self._lock:
            frame = self._pending_frame
            frame_range = self._pending_range
            self._pending_frame = None
            self._pending_range = None
            self._scheduled = False
        if not self.connected or not self.player_to_maya:
            return
        self._applying = True
        try:
            if frame_range is not None and self.sync_range:
                first = self.to_maya(frame_range[0])
                last = self.to_maya(frame_range[1])
                cmds.playbackOptions(minTime=first, maxTime=last)
                self._last_sent_range = (frame_range[0], frame_range[1])
            if frame is not None:
                cmds.currentTime(self.to_maya(frame), update=True)
                self._last_sent_frame = frame
        finally:
            self._applying = False

    def _connection_lost(self, sock):
        """接続が切れたときの後片付け(メインスレッドで動く)。

        Args:
            sock (socket.socket): 切れたソケット。既に別の接続に替わっていれば何もしない。
        """
        if self._socket is sock:
            self.disconnect()

    def _notify_status(self):
        """状態が変わったことを知らせる(メインスレッドで動く)。"""
        if self.on_status is not None:
            try:
                self.on_status()
            except Exception:  # 画面の更新の失敗で連携を止めない。
                pass
