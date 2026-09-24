"""Maya API 2.0 の MPlug を属性ラッパーとして扱う。"""

import maya.cmds as cmds
import maya.api.OpenMaya as om2

from ..decorators.undo import undo_chunk


#: cmds.setAttr へ値をそのまま(型名付きで、長さ指定なし)渡せば済むスカラー配列型。
_SCALAR_ARRAY_TYPES = frozenset(("doubleArray", "floatArray", "Int32Array", "Int64Array"))

#: cmds.setAttr へ ``長さ, *値, type=...`` の形で渡す必要がある配列型。
_LENGTH_PREFIXED_ARRAY_TYPES = frozenset((
    "stringArray", "vectorArray", "floatVectorArray", "pointArray", "matrixArray",
    "componentList",
))


class Plug:
    """Maya API 2.0 の MPlug を保持する属性ラッパー。

    Plug(node, mplug) は配列・登録済み属性型・複合属性の順で
    専用クラスを選択する。基底クラスの書き込み・接続・ロック操作は
    Undo チャンクで囲まれる。派生クラス独自の経路は各メソッドを参照する。"""

    _registry = None  #: initialize_plug_api() が構築後に注入する PlugRegistry。

    def __new__(cls, node, mplug):
        """配列・登録属性型・複合属性の順にラッパー型を選ぶ。

        Args:
            node (Node): プラグを所有するノードラッパー。
            mplug (om2.MPlug): ラップする Maya API 2.0 のプラグ。

        Returns:
            Plug: 適切な派生クラスのインスタンス。派生クラスから直接呼んだ場合はそのクラスを割り当てる。
        """
        if cls is Plug:
            # ArrayPlug/CompoundPlug との循環importを避けるため呼び出し時に遅延importする。
            from .array_plug import ArrayPlug
            from .compound_plug import CompoundPlug

            wrapped = om2.MPlug(mplug)
            if wrapped.isArray:
                return ArrayPlug(node, mplug)
            if cls._registry is not None:
                attr_type = cmds.getAttr(wrapped.name(), type=True)
                resolved_class = cls._registry.lookup(attr_type)
                if resolved_class is not None:
                    return resolved_class(node, mplug)
            if wrapped.isCompound:
                return CompoundPlug(node, mplug)
        return super().__new__(cls)

    def __init__(self, node, mplug):
        """所有ノードと API 2.0 MPlug のコピーを保持する。

        Args:
            node (Node): プラグを所有するノードラッパー。
            mplug (om2.MPlug): ラップする Maya API 2.0 のプラグ。

        Returns:
            None: 値を返さない。
        """
        self._node = node
        self._mplug = om2.MPlug(mplug)

    def mplug(self):
        """内部で保持する Maya API 2.0 MPlug を返す。

        Returns:
            om2.MPlug: ラップ対象のプラグ。
        """
        return self._mplug

    @property
    def node(self):
        """この Plug を所有する hlib ノードを取得する。

        Returns:
            Node: 所有ノード。
        """
        return self._node

    @property
    def name(self):
        """ノード名を含まない短いプラグ名を取得する。

        Returns:
            str: 必要な multi インデックスを含むプラグ名。
        """
        return self._mplug.partialName(
            includeNodeName=False,
            includeNonMandatoryIndices=True,
            useLongNames=False,
        )

    @property
    def full_name(self):
        """ノード名を含む完全修飾プラグ名を取得する。

        Returns:
            str: ``node.attribute`` 形式のプラグ名。
        """
        return self._mplug.name()

    @property
    def attribute(self):
        """基になる Maya 属性のロング名を取得する。

        Returns:
            str: MFnAttribute が返す属性名。
        """
        return om2.MFnAttribute(self._mplug.attribute()).name

    def nice_name(self):
        """UI 表示用のニース名を取得する。

        Returns:
            str: Attribute Editor 等で使われる表示名(例: ``translateX`` は
                ``"Translate X"``)。
        """
        return cmds.attributeName(self.full_name, nice=True)

    def type(self):
        """このプラグを表す現在の hlib クラスを返す。

        Returns:
            type: 解決済みの Plug サブクラス（例: ``DoubleLinearPlug``）。
        """
        return type(self)

    @property
    def is_array(self):
        """multi 属性か判定する。

        Returns:
            bool: array プラグの場合は ``True``。
        """
        return self._mplug.isArray

    @property
    def is_compound(self):
        """compound 属性か判定する。

        Returns:
            bool: 子プラグを持つ場合は ``True``。
        """
        return self._mplug.isCompound

    @property
    def is_element(self):
        """multi 属性の要素プラグか判定する。

        Returns:
            bool: array 要素の場合は ``True``。
        """
        return self._mplug.isElement

    @property
    def is_child(self):
        """compound 属性の子プラグか判定する。

        Returns:
            bool: 子プラグの場合は ``True``。
        """
        return self._mplug.isChild

    @property
    def parent(self):
        """compound 属性の子プラグであれば、その親プラグを取得する。

        Returns:
            Plug | None: 親プラグ。子プラグでない場合は ``None``。
        """
        if not self._mplug.isChild:
            return None
        return Plug(self._node, self._mplug.parent())

    @property
    def is_keyable(self):
        """チャンネルボックスでキー可能な属性か判定する。

        setAttr(keyable=...) によるプラグ単位の動的な上書きを反映する
        （属性定義の既定値だけを見る MFnAttribute.keyable とは異なる）。

        Returns:
            bool: キー可能な場合は ``True``。
        """
        return self._mplug.isKeyable

    @undo_chunk("hlibPlugSetKeyable")
    def set_keyable(self, state):
        """キー可能状態を変更する。

        Args:
            state (bool): ``True`` でキー可能にする。``False`` にするとチャンネル
                ボックスからも隠れる（``set_channel_box(True)`` で明示的に表示可能）。

        Returns:
            Plug: 自身。
        """
        cmds.setAttr(self.full_name, keyable=bool(state))
        return self

    @undo_chunk("hlibPlugSetChannelBox")
    def set_channel_box(self, state):
        """キー不可のままチャンネルボックスへの表示状態を変更する。

        Args:
            state (bool): ``True`` でチャンネルボックスに表示する。``False`` で隠す。

        Returns:
            Plug: 自身。
        """
        cmds.setAttr(self.full_name, channelBox=bool(state))
        return self

    @property
    def is_connected(self):
        """入出力接続を持つか判定する。

        Returns:
            bool: 何らかの接続を持つ場合は ``True``。
        """
        return self._mplug.isConnected

    @property
    def is_source(self):
        """出力接続元か判定する。

        Returns:
            bool: 他のプラグへの出力接続を持つ場合は ``True``。
        """
        return self._mplug.isSource

    @property
    def is_destination(self):
        """入力接続先か判定する。

        Returns:
            bool: 他のプラグからの入力接続を持つ場合は ``True``。
        """
        return self._mplug.isDestination

    @property
    def is_hidden(self):
        """UI から隠された属性か判定する。

        Returns:
            bool: 隠し属性の場合は ``True``。
        """
        return om2.MFnAttribute(self._mplug.attribute()).hidden

    @property
    def is_dynamic(self):
        """動的に追加された属性（addAttr によるカスタム属性等）か判定する。

        Returns:
            bool: 動的属性の場合は ``True``。静的（ノード型に組み込み）の属性は ``False``。
        """
        return om2.MFnAttribute(self._mplug.attribute()).dynamic

    @property
    def is_readable(self):
        """値を取得できる属性か判定する。

        Returns:
            bool: 読み取り可能な場合は ``True``。
        """
        return om2.MFnAttribute(self._mplug.attribute()).readable

    @property
    def is_writable(self):
        """値を設定できる属性か判定する。

        Returns:
            bool: 書き込み可能な場合は ``True``。
        """
        return om2.MFnAttribute(self._mplug.attribute()).writable

    @property
    def is_storable(self):
        """シーンファイルへ値が保存される属性か判定する。

        Returns:
            bool: 保存対象の場合は ``True``。
        """
        return om2.MFnAttribute(self._mplug.attribute()).storable

    @property
    def has_min(self):
        """最小値制限を持つ属性か判定する。

        数値属性、角度・距離・時間属性のみ対応する。それ以外は常に ``False``。

        Returns:
            bool: 最小値制限を持つ場合は ``True``。
        """
        attr = self._mplug.attribute()
        if attr.hasFn(om2.MFn.kNumericAttribute):
            return om2.MFnNumericAttribute(attr).hasMin()
        if attr.hasFn(om2.MFn.kUnitAttribute):
            return om2.MFnUnitAttribute(attr).hasMin()
        return False

    @property
    def has_max(self):
        """最大値制限を持つ属性か判定する。

        数値属性、角度・距離・時間属性のみ対応する。それ以外は常に ``False``。

        Returns:
            bool: 最大値制限を持つ場合は ``True``。
        """
        attr = self._mplug.attribute()
        if attr.hasFn(om2.MFn.kNumericAttribute):
            return om2.MFnNumericAttribute(attr).hasMax()
        if attr.hasFn(om2.MFn.kUnitAttribute):
            return om2.MFnUnitAttribute(attr).hasMax()
        return False

    @property
    def min(self):
        """設定されている最小値を取得する。

        数値属性は ``float``、角度・距離・時間属性は対応する Maya API 2.0 の
        単位付きオブジェクト（``MAngle``/``MDistance``/``MTime``）をそのまま返す。
        誤った単位換算を避けるため、内部でのラジアン/センチメートル変換は行わない。

        Returns:
            float | om2.MAngle | om2.MDistance | om2.MTime | None: 最小値。
                制限が無い、または対応しない属性型では ``None``。
        """
        attr = self._mplug.attribute()
        if attr.hasFn(om2.MFn.kNumericAttribute):
            fn = om2.MFnNumericAttribute(attr)
            return fn.getMin() if fn.hasMin() else None
        if attr.hasFn(om2.MFn.kUnitAttribute):
            fn = om2.MFnUnitAttribute(attr)
            return fn.getMin() if fn.hasMin() else None
        return None

    @property
    def max(self):
        """設定されている最大値を取得する。

        数値属性は ``float``、角度・距離・時間属性は対応する Maya API 2.0 の
        単位付きオブジェクト（``MAngle``/``MDistance``/``MTime``）をそのまま返す。

        Returns:
            float | om2.MAngle | om2.MDistance | om2.MTime | None: 最大値。
                制限が無い、または対応しない属性型では ``None``。
        """
        attr = self._mplug.attribute()
        if attr.hasFn(om2.MFn.kNumericAttribute):
            fn = om2.MFnNumericAttribute(attr)
            return fn.getMax() if fn.hasMax() else None
        if attr.hasFn(om2.MFn.kUnitAttribute):
            fn = om2.MFnUnitAttribute(attr)
            return fn.getMax() if fn.hasMax() else None
        return None

    @property
    def has_soft_min(self):
        """ソフト最小値（UIスライダーの下限）を持つ属性か判定する。

        数値属性、角度・距離・時間属性のみ対応する。それ以外は常に ``False``。

        Returns:
            bool: ソフト最小値を持つ場合は ``True``。
        """
        attr = self._mplug.attribute()
        if attr.hasFn(om2.MFn.kNumericAttribute):
            return om2.MFnNumericAttribute(attr).hasSoftMin()
        if attr.hasFn(om2.MFn.kUnitAttribute):
            return om2.MFnUnitAttribute(attr).hasSoftMin()
        return False

    @property
    def has_soft_max(self):
        """ソフト最大値（UIスライダーの上限）を持つ属性か判定する。

        数値属性、角度・距離・時間属性のみ対応する。それ以外は常に ``False``。

        Returns:
            bool: ソフト最大値を持つ場合は ``True``。
        """
        attr = self._mplug.attribute()
        if attr.hasFn(om2.MFn.kNumericAttribute):
            return om2.MFnNumericAttribute(attr).hasSoftMax()
        if attr.hasFn(om2.MFn.kUnitAttribute):
            return om2.MFnUnitAttribute(attr).hasSoftMax()
        return False

    @property
    def soft_min(self):
        """設定されているソフト最小値（UIスライダーの下限）を取得する。

        数値属性は ``float``、角度・距離・時間属性は対応する Maya API 2.0 の
        単位付きオブジェクトをそのまま返す。min/max とは異なり値の入力自体は制限しない。

        Returns:
            float | om2.MAngle | om2.MDistance | om2.MTime | None: ソフト最小値。
                制限が無い、または対応しない属性型では ``None``。
        """
        attr = self._mplug.attribute()
        if attr.hasFn(om2.MFn.kNumericAttribute):
            fn = om2.MFnNumericAttribute(attr)
            return fn.getSoftMin() if fn.hasSoftMin() else None
        if attr.hasFn(om2.MFn.kUnitAttribute):
            fn = om2.MFnUnitAttribute(attr)
            return fn.getSoftMin() if fn.hasSoftMin() else None
        return None

    @property
    def soft_max(self):
        """設定されているソフト最大値（UIスライダーの上限）を取得する。

        数値属性は ``float``、角度・距離・時間属性は対応する Maya API 2.0 の
        単位付きオブジェクトをそのまま返す。min/max とは異なり値の入力自体は制限しない。

        Returns:
            float | om2.MAngle | om2.MDistance | om2.MTime | None: ソフト最大値。
                制限が無い、または対応しない属性型では ``None``。
        """
        attr = self._mplug.attribute()
        if attr.hasFn(om2.MFn.kNumericAttribute):
            fn = om2.MFnNumericAttribute(attr)
            return fn.getSoftMax() if fn.hasSoftMax() else None
        if attr.hasFn(om2.MFn.kUnitAttribute):
            fn = om2.MFnUnitAttribute(attr)
            return fn.getSoftMax() if fn.hasSoftMax() else None
        return None

    @property
    def default(self):
        """属性の既定値を取得する。

        数値属性は ``float``/``bool``、角度・距離・時間属性は対応する Maya API 2.0
        の単位付きオブジェクト、enum 属性は ``int`` をそのまま返す。

        Returns:
            object | None: 既定値。対応しない属性型では ``None``。
        """
        attr = self._mplug.attribute()
        if attr.hasFn(om2.MFn.kNumericAttribute):
            return om2.MFnNumericAttribute(attr).default
        if attr.hasFn(om2.MFn.kUnitAttribute):
            return om2.MFnUnitAttribute(attr).default
        if attr.hasFn(om2.MFn.kEnumAttribute):
            return om2.MFnEnumAttribute(attr).default
        return None

    def enum_name(self):
        """enum 属性の現在値に対応するフィールド名を取得する。

        Returns:
            str: 現在値に対応するフィールド名。

        Raises:
            TypeError: enum 属性でない場合。
        """
        attr = self._mplug.attribute()
        if not attr.hasFn(om2.MFn.kEnumAttribute):
            raise TypeError("enum_name は enum 属性にのみ使用できます")
        return om2.MFnEnumAttribute(attr).fieldName(int(self.get()))

    def enum_value(self, name):
        """enum 属性のフィールド名に対応する値を取得する(enum_name の逆引き)。

        Args:
            name (str): 検索するフィールド名。

        Returns:
            int: name に対応する enum 値。

        Raises:
            TypeError: enum 属性でない場合。
            ValueError: name に一致するフィールドが無い場合。
        """
        attr = self._mplug.attribute()
        if not attr.hasFn(om2.MFn.kEnumAttribute):
            raise TypeError("enum_value は enum 属性にのみ使用できます")
        enum_fn = om2.MFnEnumAttribute(attr)
        for value in range(enum_fn.getMin(), enum_fn.getMax() + 1):
            try:
                if enum_fn.fieldName(value) == name:
                    return value
            except RuntimeError:
                continue
        raise ValueError(f"No enum field named {name!r}")

    @property
    def is_locked(self):
        """プラグがロックされているか判定する。

        Returns:
            bool: ロックされている場合は ``True``。
        """
        return self._mplug.isLocked

    @undo_chunk("hlibPlugLock")
    def set_locked(self, state):
        """プラグのロック状態を変更する。

        Args:
            state (bool): ``True`` でロック、``False`` で解除する。

        Returns:
            Plug: 自身。
        """
        cmds.setAttr(self.full_name, lock=bool(state))
        return self

    @property
    def is_muted(self):
        """アトリビュートがミュートされているか判定する。

        Returns:
            bool: ミュートされている場合は ``True``。
        """
        return bool(cmds.mute(self.full_name, query=True))

    @undo_chunk("hlibPlugMute")
    def mute(self):
        """アトリビュートをミュートする（現在の出力値で固定する）。

        Returns:
            Plug: 自身。

        Raises:
            RuntimeError: Maya がミュートを拒否した場合。
        """
        cmds.mute(self.full_name)
        return self

    @undo_chunk("hlibPlugUnmute")
    def unmute(self):
        """アトリビュートのミュートを解除する。

        Returns:
            Plug: 自身。
        """
        cmds.mute(self.full_name, disable=True, force=True)
        return self

    @undo_chunk("hlibPlugDeleteAttr")
    def delete_attr(self, force=False):
        """この属性をノードから削除する。

        動的に追加された属性（addAttr によるカスタム属性）にのみ使用できる。
        静的（ノード型に組み込み）の属性を削除しようとすると Maya が拒否する。
        接続がある場合は force に関わらず Maya が自動的に切断してから削除する。

        Args:
            force (bool): True の場合、ロックされていれば一時的に解除してから
                削除する。False でロックされている属性を削除しようとすると
                RuntimeError になる。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: force=False でロックされている場合や、静的属性の
                削除を試みた場合など、Maya が削除を拒否した場合。
        """
        if force and self.is_locked:
            cmds.setAttr(self.full_name, lock=False)
        cmds.deleteAttr(self.full_name)

    def get(self, ws=False):
        """評価済みの Maya 属性値を取得する。

        bool/int/float 系の数値属性、角度・距離・時間の単位属性、enum、
        文字列属性は Maya API 2.0(MPlug)経由で直接読み取り、MEL コマンドの
        往復を避ける。角度は度、距離・時間は現在の UI 単位で返し、
        ``cmds.getAttr`` の既定挙動と一致させる。message 属性や mesh/カーブ等の
        複雑な typed data 属性のように対応する読み取り方法が無いものは
        ``cmds.getAttr`` にフォールバックする。

        Args:
            ws (bool): ワールド空間値を要求する。汎用 scalar Plug では無視される。

        Returns:
            object: 属性値。1要素のリストにタプルが入っている場合のみ、
                そのタプルを返す（cmds.getAttr フォールバック時のみ該当）。
                文字列、数値、配列、None など実際の属性型に依存する。
        """
        attr = self._mplug.attribute()
        if attr.hasFn(om2.MFn.kNumericAttribute):
            value = self._get_numeric_value(attr)
            if value is not None:
                return value
        elif attr.hasFn(om2.MFn.kUnitAttribute):
            value = self._get_unit_value(attr)
            if value is not None:
                return value
        elif attr.hasFn(om2.MFn.kEnumAttribute):
            return self._mplug.asInt()
        elif attr.hasFn(om2.MFn.kTypedAttribute) and om2.MFnTypedAttribute(attr).attrType() == om2.MFnData.kString:
            return self._mplug.asString()

        value = cmds.getAttr(self.full_name)
        if isinstance(value, list) and len(value) == 1 and isinstance(value[0], tuple):
            return tuple(value[0])
        return value

    def _get_numeric_value(self, attr):
        """MFnNumericAttribute の値を対応する Python 型で取得する。

        Args:
            attr (om2.MObject): 数値属性の MObject。

        Returns:
            bool | int | float | None: 値。bool/byte/short/int/long/float/double
                以外の数値型(複合型など)は ``None`` (呼び出し側で cmds.getAttr
                へフォールバックする)。
        """
        numeric_type = om2.MFnNumericAttribute(attr).numericType()
        if numeric_type == om2.MFnNumericData.kBoolean:
            return self._mplug.asBool()
        if numeric_type in (
            om2.MFnNumericData.kByte,
            om2.MFnNumericData.kShort,
            om2.MFnNumericData.kInt,
            om2.MFnNumericData.kLong,
        ):
            return self._mplug.asInt()
        if numeric_type in (om2.MFnNumericData.kFloat, om2.MFnNumericData.kDouble):
            return self._mplug.asDouble()
        return None

    def _get_unit_value(self, attr):
        """MFnUnitAttribute の値を Maya の現在の UI 単位で取得する。

        cmds.getAttr と同じく、角度は度、距離・時間は現在の UI 単位に変換する。

        Args:
            attr (om2.MObject): 角度・距離・時間属性の MObject。

        Returns:
            float | None: UI 単位での値。対応しない単位種別では ``None``。
        """
        unit_type = om2.MFnUnitAttribute(attr).unitType()
        if unit_type == om2.MFnUnitAttribute.kAngle:
            return self._mplug.asMAngle().asDegrees()
        if unit_type == om2.MFnUnitAttribute.kDistance:
            return self._mplug.asMDistance().asUnits(om2.MDistance.uiUnit())
        if unit_type == om2.MFnUnitAttribute.kTime:
            return self._mplug.asMTime().asUnits(om2.MTime.uiUnit())
        return None

    @undo_chunk("hlibPlugSet")
    def set(self, value):
        """プラグ値を変更する。

        doubleArray/floatArray/Int32Array/Int64Array のようなスカラー配列型と、
        stringArray/vectorArray/floatVectorArray/pointArray/matrixArray/
        componentList のような長さ指定が必要な配列型は、``cmds.setAttr`` が
        要求する引数の形(単純な ``*value`` 展開ではなく、型名や要素数の
        明示)が数値コンパウンド(double3 等)や matrix と異なるため、
        ``cmds.getAttr(..., type=True)`` で実際の属性型を判定してから
        対応する形で呼び出す。それ以外の型(数値コンパウンド、matrix 等)は
        従来通り ``*value`` で展開する。

        Args:
            value (object): 設定する Maya 互換値。

        Returns:
            Plug: 自身。
        """
        if isinstance(value, str):
            cmds.setAttr(self.full_name, value, type="string")
            return self
        if isinstance(value, (tuple, list)):
            attr_type = cmds.getAttr(self.full_name, type=True)
            if attr_type in _SCALAR_ARRAY_TYPES:
                cmds.setAttr(self.full_name, value, type=attr_type)
            elif attr_type in _LENGTH_PREFIXED_ARRAY_TYPES:
                cmds.setAttr(self.full_name, len(value), *value, type=attr_type)
            else:
                cmds.setAttr(self.full_name, *value)
            return self
        cmds.setAttr(self.full_name, value)
        return self

    @undo_chunk("hlibPlugReset")
    def reset(self):
        """数値・単位・enum属性を定義上の既定値へ戻す。

        単位属性は現在のMaya表示単位へ変換する。複合属性は子ごとに処理する。
        接続の切断やロック解除はしない。失敗前の変更は自動では戻さない。

        Returns:
            Plug: 自身。一回のUndoで全変更を戻せる。

        Raises:
            TypeError: 配列全体・文字列・messageなど既定値を扱えない属性の場合。
            RuntimeError: ロック・入力接続などで変更できない場合。
        """
        if self.is_array:
            raise TypeError("Reset an array element instead of the array plug")
        if self._mplug.isCompound:
            for index in range(self._mplug.numChildren()):
                Plug(self._node, self._mplug.child(index)).reset()
            return self
        value = self.default
        if value is None:
            raise TypeError(f"No supported default value for {self.full_name}")
        if isinstance(value, om2.MAngle):
            value = value.asUnits(om2.MAngle.uiUnit())
        elif isinstance(value, om2.MDistance):
            value = value.asUnits(om2.MDistance.uiUnit())
        elif isinstance(value, om2.MTime):
            value = value.asUnits(om2.MTime.uiUnit())
        self.set(value)
        return self

    def source(self):
        """入力接続元の Plug を取得する。

        Returns:
            Plug | None: 接続元。入力接続がない場合は ``None``。
        """
        sources = self._mplug.connectedTo(True, False)
        return Plug(self._node_from_mplug(sources[0]), sources[0]) if sources else None

    def anim_curve(self):
        """このプラグに直接接続された animCurve ノードを取得する。

        pairBlend やアニメーションレイヤーを介した間接的な animCurve は解決しない
        （直接の入力接続だけを対象とする）。

        Returns:
            Node | None: 接続されている animCurve ノード。無ければ ``None``。
        """
        sources = self._mplug.connectedTo(True, False)
        if not sources:
            return None
        source_mobject = sources[0].node()
        if not source_mobject.hasFn(om2.MFn.kAnimCurve):
            return None
        return self._node_from_mplug(sources[0])

    def destinations(self):
        """出力接続先の Plug をすべて取得する。

        Returns:
            list[Plug]: 接続先プラグ。
        """
        return [Plug(self._node_from_mplug(plug), plug) for plug in self._mplug.connectedTo(False, True)]

    def is_connected_to(self, other):
        """指定したプラグと接続されているか判定する。

        入力・出力いずれの向きでも一致すれば True を返す。

        Args:
            other (Plug): 判定対象のプラグ。

        Returns:
            bool: 接続されている場合は True。

        Raises:
            TypeError: other が Plug でない場合。
        """
        other = self._coerce_plug(other)
        return any(
            connected == other.mplug()
            for connected in self._mplug.connectedTo(True, True)
        )

    @undo_chunk("hlibPlugConnect")
    def connect(self, target, force=False):
        """このプラグを別のプラグへ接続する。

        target がロックされている場合、``cmds.connectAttr(force=True)`` は
        既存の入力接続を置き換えられても、ロック自体は解除しないため失敗する。
        force=True 指定時は、target がロックされていれば接続の前後で
        一時的にアンロック・再ロックする(ロックされていなければ何もしない)。
        一連の操作は一回の Undo にまとまる。

        Args:
            target (Plug): 接続先プラグ。
            force (bool): 既存入力接続を強制的に置き換えるか。ロックされた
                target への接続もこの場合のみ一時アンロックして許可する。

        Returns:
            Plug: 接続先プラグ。

        Raises:
            TypeError: target が Plug でない場合。
        """
        target = self._coerce_plug(target)
        should_unlock = force and target.is_locked
        if should_unlock:
            target.set_locked(False)
        try:
            cmds.connectAttr(self.full_name, target.full_name, force=force)
        finally:
            if should_unlock:
                target.set_locked(True)
        return target

    @undo_chunk("hlibPlugDisconnect")
    def disconnect(self, target=None):
        """プラグ接続を解除する。

        Args:
            target (Plug | None): 明示的に解除する接続先。省略時は入力元と全出力先を
                解除する。

        Returns:
            Plug: 自身。

        Raises:
            TypeError: target が None または Plug 以外の場合。
            RuntimeError: Maya が接続解除を拒否した場合。
        """
        if target is not None:
            target = self._coerce_plug(target)
            cmds.disconnectAttr(self.full_name, target.full_name)
            return self
        source = self.source()
        if source is not None:
            cmds.disconnectAttr(source.full_name, self.full_name)
        for destination in self.destinations():
            cmds.disconnectAttr(self.full_name, destination.full_name)
        return self

    def __str__(self):
        """完全修飾した Maya プラグ名を返す。

        Returns:
            str: ノード名を含むプラグ名。
        """
        return self.full_name

    def __repr__(self):
        """デバッグ用に完全修飾プラグ名を含む表現を返す。

        Returns:
            str: Plug と完全修飾プラグ名を含む文字列表現。
        """
        return f"Plug({self.full_name!r})"

    @staticmethod
    def _coerce_plug(value):
        """接続先入力が Plug であることを検証する。

        Args:
            value (object): 型を確認する入力。

        Returns:
            Plug: 入力と同じオブジェクト。

        Raises:
            TypeError: value が Plug またはその派生クラスでない場合。
        """
        if not isinstance(value, Plug):
            raise TypeError("target must be an hlib Plug")
        return value

    @staticmethod
    def _node_from_mplug(mplug):
        """MPlug の所有 MObject から汎用 Node ラッパーを生成する。

        Args:
            mplug (om2.MPlug): 所有ノードを取得するプラグ。

        Returns:
            Node: 所有ノードの型登録に従って解決したラッパー。
        """
        # nodes.node が ..plugs.plug を逆方向 import するため、
        # 循環回避のためここで遅延 import する（hlib で意図的な相互依存の一つ）。
        from ..nodes.node import Node

        return Node(mplug.node())
