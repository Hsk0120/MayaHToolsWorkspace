# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""ノードのアニメーション(時間入力のアニメカーブとアニメーションレイヤー)を保存・復元する。"""

import math
import maya.cmds as cmds
from ..decorator import _require_bool
from ..nodes.node import Node
from ._animCurveData import _check_curve, _is_time_input, _merge_keys, _output_kind, _read_curve, _transform_keys, _write_curve
from .plugRef import PlugRef
from .snapshot import Snapshot
from typing import Iterable
from mlib.json.nameMapping import NameMapping
from mlib.json.snapshot import ValidationReport
from mlib.plugs.plug import Plug

_MODES: tuple
_LAYER_FLAGS: tuple
_LAYER_ENUMS: tuple


class AnimationSnapshot(Snapshot):
    """ノードのアトリビュートにつながる時間入力のアニメカーブを、アニメーションレイヤーごとに保持する。

    カーブはキーの時刻・値、接線の型・角度・ウェイト、接線とウェイトのロック、ブレークダウン、
    ウェイト付き接線、前後のインフィニティまで保存し、同じ形に作り直す。値はmlibの既定の単位
    (角度は度、距離はcm)、時刻は保存時のUI時間単位のフレームで保存するため、適用時のUI単位に左右されない。
    アニメーションレイヤーに入ったアトリビュートは、ベースレイヤーと各レイヤーのカーブを別々に保存し、
    レイヤーの設定(ウェイト・ミュート・ソロ・ロック・オーバーライド・パススルー・回転と
    スケールの累積モード・親レイヤー)も保存する。ドリブンキー(単位なし入力のカーブ)は
    :class:`~mlib.json.drivenKeysSnapshot.DrivenKeysSnapshot` で扱う。

    データの形::

        {"timeRange": [1.0, 24.0] or None, "rootLayer": "BaseAnimation" or None,
         "layers": [{"name": "L1", "parent": None, "weight": 1.0, "mute": False, "solo": False, "lock": False,
                     "override": False, "passthrough": True, "rotationAccumulationMode": "...",
                     "scaleAccumulationMode": "..."}, ...],
         "curves": [{"plug": {<PlugRef>}, "layer": None or "L1", "curve": {<カーブ>}}, ...]}

    ``layer`` がNoneのカーブはベースレイヤー(レイヤーが無ければアトリビュートへ直接つながるカーブ)。
    カーブの辞書の形は ``mlib/json/_animCurveData.py`` の説明を参照する。

    Examples:
        >>> anim = AnimationSnapshot.capture(mlib.ls(type="joint"), time=(1, 24))
        >>> anim.save("walk.json")
        >>> AnimationSnapshot.load("walk.json").apply(namespaceMap={"chrA": "chrB"}, mode="insert", timeOffset=100)
    """
    FORMAT: str
    VERSION: int
    @classmethod
    def capture(cls, nodes: Iterable[Node | str], *, time: tuple[float, float] | None = ...) -> AnimationSnapshot:
        """ノードのアトリビュートにつながる時間入力のアニメカーブとアニメーションレイヤーを取得する。

        アトリビュートへ直接つながるカーブと、アニメーションレイヤーに入ったアトリビュートの
        ベースレイヤー・各レイヤーのカーブを対象にする。キーが1つも無い(範囲内に無い)カーブは保存しない。
        保存したレイヤーの親レイヤーも、ルート(BaseAnimation)を除いて保存する。

        Args:
            nodes (Iterable[Node | str]): 対象のノード。1つのNode・名前も受け付ける。
            time (tuple[float, float] | None): 両端を含む時刻の範囲(現在のUI時間単位のフレーム)。
                範囲内のキーだけを保存する。Noneは全キー。

        Returns:
            AnimationSnapshot: 取得したカーブを持つ新しいインスタンス。

        Raises:
            TypeError: nodesがノードまたはその並びでない、またはtimeが2つの数値の並びでない場合。
            ValueError: timeが有限でない、または開始が終了より大きい場合。
            RuntimeError: ノードが存在しない場合。
        """
        ...
    def apply(self, *, nameMap: dict[str, str] | None = ..., replace: Iterable[tuple[str, str]] | None = ..., namespaceMap: dict[str, str] | None = ..., mode: str = ..., timeOffset: float = ..., timing: str = ..., createLayers: bool = ..., fast: bool = ...) -> ValidationReport:
        """保存したカーブを、対応付けたノードのアトリビュートへ書き戻す。

        カーブが無いアトリビュートには新しく作る。通常は1回のUndoにまとめ、途中で失敗したら巻き戻す。
        見つからないノード・アトリビュートは ``missing``、ロックされたアトリビュート、アニメカーブ・
        アニメーションレイヤー以外(コンストレイント・ドリブンキー等)が入力につながったアトリビュート、
        出力の種類(角度・距離等)が違うカーブ、見つからない・ロックされたレイヤーのカーブは
        ``skipped`` に記録して飛ばし、まとめて警告する。

        Args:
            nameMap (dict[str, str] | None): 名前空間を除いた名前の対応表。
            replace (Iterable[tuple[str, str]] | None): 順に当てる文字列置換。
            namespaceMap (dict[str, str] | None): 名前空間の対応。レイヤー名には当てない。
            mode (str): 既存のキーの扱い。``"replace"`` (既定)はカーブごと入れ替える(ウェイト付き接線・
                インフィニティも保存した値にする)。``"insert"`` は保存した範囲(``capture`` の ``time``、
                省略時はカーブごとの最初と最後のキー。timeOffset後)のキーだけを置き換え、範囲外のキーを残す。
                ``"merge"`` は同じ時刻のキーだけを上書きし、ほかの既存のキーを残す。insert・mergeでは既存の
                カーブのウェイト付き接線・インフィニティを保つ。
            timeOffset (float): キーの時刻へ足す量(現在のUI時間単位のフレーム)。
            timing (str): 保存時とfpsが違う場合の扱い。``"frame"`` (既定)はフレーム番号を保ち、
                ``"second"`` は秒を保つように時刻と接線を換算する。
            createLayers (bool): Trueは見つからないレイヤーを保存した設定で作る(既定)。同じ名前の
                レイヤーがあれば設定を変えずに使う。Falseは見つからないレイヤーのカーブを飛ばす。
            fast (bool): TrueはUndoに記録せず、キーをOpenMayaで書く(通常の約4倍速い)。既定False。
                途中で失敗しても巻き戻さない。

        Returns:
            ValidationReport: 適用の結果。

        Raises:
            TypeError: timeOffsetが数値でない、またはcreateLayers・fastがbool以外の場合。
            ValueError: modeが対応外、timeOffsetが有限でない、またはtimingが ``"frame"``・``"second"``
                以外の場合。
        """
        ...
    def _check_data(self, data: dict):
        """``curves``・``layers`` の形を確かめる。

        Args:
            data (dict): 保持する前のデータ。

        Raises:
            ValueError: データの形が違う場合。
        """
        ...
    def _validate(self, mapping: NameMapping, report: ValidationReport, options: dict):
        """見つからないノード・アトリビュートを記録する。

        Args:
            mapping (NameMapping): 名前の対応付け。
            report (ValidationReport): 記録先。
            options (dict): 使わない。
        """
        ...
    def _apply(self, mapping: NameMapping, report: ValidationReport, options: dict, fast: bool):
        """カーブを書き込む。fastではcmdsの部分(カーブ・レイヤーの作成)もUndoに記録しない。

        Args:
            mapping (NameMapping): 名前の対応付け。
            report (ValidationReport): 記録先。
            options (dict): mode・timeOffset・timing・createLayers。
            fast (bool): TrueはUndoなしでOpenMayaを使う。
        """
        ...
    def _apply_curves(self, mapping: NameMapping, report: ValidationReport, options: dict, fast: bool):
        """保存したカーブを順に書き込み、作ったレイヤーのロックを最後に戻す。

        Args:
            mapping (NameMapping): 名前の対応付け。
            report (ValidationReport): 記録先。
            options (dict): mode・timeOffset・timing・createLayers。
            fast (bool): TrueはキーをOpenMayaで書く。
        """
        ...


class _LayerResolver:
    """保存したレイヤー名を、シーンのアニメーションレイヤーへ対応付ける(必要なら作る)。"""
    def __init__(self, layers: list[dict], create: bool) -> None:
        """保存したレイヤーの設定を保持する。

        Args:
            layers (list[dict]): 保存したレイヤーの設定(親が先)。
            create (bool): 見つからないレイヤーを作るか。
        """
        ...
    def resolve(self, name: str) -> tuple[str | None, str]:
        """レイヤー名に対応するシーンのレイヤーを返す。

        Args:
            name (str): 保存したレイヤー名。

        Returns:
            tuple[str | None, str]: レイヤー名と、使えない場合の理由。
        """
        ...
    def restoreLocks(self):
        """作ったレイヤーのうち、保存時にロックされていたものをロックする。"""
        ...
    def _find_or_create(self, name: str) -> tuple[str | None, str]:
        """既存のレイヤーを使うか、保存した設定で作る。

        Args:
            name (str): 保存したレイヤー名。

        Returns:
            tuple[str | None, str]: レイヤー名と、使えない場合の理由。
        """
        ...

def _require_nodes(nodes: object) -> list[Node]:
    """ノード・名前・その並びを、Nodeのlistにする。

    Args:
        nodes (object): 対象のノード。

    Returns:
        list[Node]: 対象のノード。

    Raises:
        TypeError: ノード・名前・その並びでない場合。
        RuntimeError: ノードが存在しない場合。
    """
    ...

def _require_time_range(time: object) -> tuple[float, float] | None:
    """時刻の範囲を検証する。

    Args:
        time (object): Noneまたは ``(start, end)``。

    Returns:
        tuple[float, float] | None: 範囲。

    Raises:
        TypeError: 2つの数値の並びでない場合。
        ValueError: 有限でない、または開始が終了より大きい場合。
    """
    ...

def _check_layer(layer: object, names: list[str]):
    """保存したレイヤーの設定の形を確かめる。

    Args:
        layer (object): レイヤーの設定。
        names (list[str]): それより前に出たレイヤー名(親は先に出る)。

    Raises:
        ValueError: 形・型が違う場合。
    """
    ...

def _layer_members() -> dict[str, list[str]]:
    """アニメーションレイヤーに入ったアトリビュートを、ノードの完全パスごとに集める。

    Returns:
        dict[str, list[str]]: ノードの完全パスと、アトリビュートのパスの並び(重複なし)。
            レイヤーが無ければ空の辞書。
    """
    ...

def _node_curves(full: str, layered: list[str], root: str | None) -> list[tuple[str, str | None, str]]:
    """ノードのアトリビュートにつながる時間入力のカーブを集める。

    Args:
        full (str): ノードの完全パス。
        layered (list[str]): アニメーションレイヤーに入ったアトリビュートのパス。
        root (str | None): ルートレイヤー名。

    Returns:
        list[tuple[str, str | None, str]]: (アトリビュートのパス, レイヤー名(ベースはNone), カーブ名)。
    """
    ...

def _capture_layers(used: list[str], root: str | None) -> list[dict]:
    """使ったレイヤーとその親(ルートを除く)の設定を、親が先の順で返す。

    Args:
        used (list[str]): カーブを保存したレイヤー名。
        root (str | None): ルートレイヤー名。

    Returns:
        list[dict]: レイヤーの設定。
    """
    ...

def _resolve_plug(entry: dict, mapping: NameMapping, report: ValidationReport) -> Plug | None:
    """カーブを書くPlugを探し、見つからなければreportへ記録する。

    Args:
        entry (dict): カーブの項目。
        mapping (NameMapping): 名前の対応付け。
        report (ValidationReport): 記録先。

    Returns:
        Plug | None: 見つかったPlug。
    """
    ...

def _target_curve(plug: str, layer: str | None, keys: list[dict]) -> tuple[str | None, str, bool]:
    """Plug(とレイヤー)のカーブを探し、無ければMayaのキー設定で作る。

    Args:
        plug (str): 書き込むPlugの名前。
        layer (str | None): レイヤー名。Noneはベース(レイヤーに入っていなければ直接つながるカーブ)。
        keys (list[dict]): 書くキー。空でカーブが無ければ何もしない。

    Returns:
        tuple[str | None, str, bool]: カーブ名、使えない場合の理由(何もしない場合は空文字列)、
            このとき作ったカーブならTrue。
    """
    ...
