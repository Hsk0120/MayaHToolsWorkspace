構成とドキュメント更新
======================

.. _tool-undo-chunk:

ツール単位のUndo
----------------

通常の利用では、hlibの編集コマンドやメソッドをそのまま呼び出します。
作成・削除・複製・グループ化・選択・キー設定・ベイク・コンストレイント作成は
各コマンド内で ``undo_chunk`` を使い、複数の内部操作を一回のUndoにまとめます。
属性・トランスフォーム・コンポーネントの編集や、ウェイト移送とjoint削除の
複合処理も、対応するメソッド内でチャンクを管理します。
複合属性の ``CompoundPlug.set()`` は全子属性を一回で戻します。
``preserved_selection()`` は選択の復元もUndo対応のコマンドで行い、
ブロック内の編集と選択変更をまとめてUndo／Redoします。
タイムスライダーの範囲変更はMayaのバージョンによりUndo対応が異なります。
各メソッドの制限を参照してください。

複数の公開操作をまとめたツールを開発するときに限り、外側でもまとめます。

.. code-block:: python

   import hlib
   from hlib.decorators import undo_chunk

   @undo_chunk("createControl")
   def create_control():
       node = hlib.createNode("transform", name="control")
       node.plug("visibility").set(False)
       return node

このツールでは作成と属性変更を一回のUndoで戻せます。内部のチャンクはネストできます。
処理ブロックをまとめる場合は ``with undo_chunk("処理名"):`` も使用できます。
デコレータには括弧が必要です。名前の省略時はMayaの既定表示を使います。

照会やラッパー取得はチャンクの対象にしません。時刻変更・UI表示・ファイル操作・
プラグイン管理など、Maya標準のUndoで戻せない操作をUndo可能にするものではありません。
``SkinCluster.set_weights()`` と ``load_weights()`` もUndo／Redoに対応します。
通常のシーン編集はUndo対応のMayaコマンドを使います。対応メソッドの
``fast=True`` はOpenMayaへ直接書き込み、Undo対象外です（:doc:`fast_edit`）。
例外時はチャンクを閉じますが、
完了済み操作を自動ロールバックしません。

例外時に完了済みの操作も自動でロールバックしたい場合は、``undo_chunk`` の代わりに
``undo_transaction`` を使用します。ブロック内で例外が発生すると、チャンクを閉じたうえで
``cmds.undo()`` を1回実行してブロック内のUndo対象操作を巻き戻してから、元の例外をそのまま
再送出します。正常終了時は ``undo_chunk`` と同様、通常の1回のUndoにまとまります。
Undoが無効な場合や ``fast=True``・ファイル操作等のUndo対象外の変更は復元できません。
ロールバック自体の失敗は抑制されるため、全変更の復元を保証するものではありません。

.. code-block:: python

   from hlib.decorators import undo_transaction

   with undo_transaction("importRig"):
       rig_root = hlib.createNode("transform", name="rig")
       # ここで例外が発生すると rig の作成も含めて全て巻き戻る
       validate_rig(rig_root)

パッケージ構成
--------------

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - パッケージ
     - 役割
   * - ``nodes``
     - Node、Transform、Joint、Mesh、NurbsCurve、IkHandle、各種 Constraint ラッパー
   * - ``plugs``
     - 属性型に応じた Plug ラッパー、配列・複合属性
   * - ``components``
     - Vertex/CV/Edge/Face/UV とその複数形。シーンを参照する座標コンポーネント
   * - ``files``
     - Scene と参照ファイル操作
   * - ``namespaces``
     - Namespace による名前空間操作
   * - ``plugins``
     - Plugin / Plugins によるプラグイン管理
   * - ``units.py`` / ``workspace.py``
     - Units による単位操作 / Workspace によるプロジェクト操作
   * - ``editors``
     - TimeSlider、Viewport、Outliner、ChannelBoxによるエディター操作
   * - ``maths``
     - OpenMaya API 2.0 の型を継承した可変の値型。Vector・Translation・Scale・Shear は
       ``MVector``、Quaternion は ``MQuaternion``、EulerRotation は ``MEulerRotation``、
       Matrix は ``MMatrix`` の派生で、om2 の関数へそのまま渡せ、演算の意味も om2 に従う
       (ハッシュ不可)。``easing`` だけは標準の ``math`` のみを使う
   * - ``cmds``
     - ``maya.cmds`` 相当の手続き的 API（createNode、ls、constraint）
   * - ``decorators``
     - Undo チャンク、選択状態の保存・復元、skinCluster変形を保ったままの
       joint姿勢編集、画面表示の一時停止
   * - ``animation`` / ``selection`` / ``json``
     - DrivenKey関係、選択スナップショット、状態のJSON保存・復元
   * - ``utils``
     - ログと進捗表示
   * - ``_core``
     - 型登録、ラッパー検出、初期化、再読み込み、コマンド入力の正規化(coerce: 文字列・
       Node・Plug・Component・om2 オブジェクトを名前・Node・Plug へ変換)の内部基盤

.. include:: _generated/full_class_diagram.rst

API の生成方針
--------------

Sphinx AutoAPI が Python ソースと docstring を静的解析します。
ビルド時に hlib・Maya を import せず、テストスクリプトも実行しません。
``__tests__`` は生成対象から除外しています。

hlib は実行時にラッパーを発見して公開 API を構成するため、
動的に追加される別名は静的解析では列挙されません。
各クラスの詳細は、定義元のモジュール（例: ``hlib.nodes.joint``）を参照してください。
継承したメソッドは基底クラスのページを参照します。
非公開メソッドと特殊メソッドも掲載し、初期化の引数は ``__init__`` の詳細に記載します。

クラスごとに独立したページを生成します。
クラスの説明の後は、hlib の API 方針(Maya へ問い合わせる処理やシーンを変える処理は
メソッド、保持している値はプロパティ)に合わせてメンバーを「メソッド」と
「プロパティ・属性」の2つのまとまりに分け、メソッドを先に掲載します。
各まとまりは、名前・シグネチャ・概要を並べた早見表と、
アルファベット順の個々の説明で構成します。
早見表では省略可能な引数を角括弧で、説明では既定値付きで表示します。
どちらにも当てはまらない種類のメンバーがあれば「その他のメンバー」に掲載します。
引数・戻り値・戻り値の型は docstring から生成し、API 名は実装に従います。
表記用テンプレートは ``_templates/autoapi/python/class.rst`` で管理し、
配色やナビゲーションは Sphinxdoc テーマと ``_static/custom.css`` を使用します。
``_templates/autoapi/python/module.rst`` は ``hlib.cmds`` のコマンドページだけを
独自の書式にし、それ以外のモジュールページは sphinx-autoapi 同梱の既定テンプレートで
生成します。
クラス継承図の Mermaid は同梱せず、``conf.py`` で版と SRI ハッシュを固定して
jsDelivr から読み込みます(図の表示にはネットワーク接続が必要です)。

更新方法
--------

関数・クラスの説明は実装の docstring を更新します。
既存コードに合わせて Google 形式の ``Args:``、``Returns:``、``Raises:`` を
使用すると、Napoleon 拡張が整形します。
引数は ``self`` / ``cls`` を除いて記載し、既定値・単位・省略時の動作を説明します。
値を返さない処理は ``Returns:`` に ``None``、ジェネレータは ``Yields:``、
必ず例外を送出する処理は ``NoReturn`` として記載します。
新しいモジュールは hlib 配下に追加すると次回ビルドで検出されます。
利用手順はこのディレクトリの ``.rst`` に記述します。

ビルド環境の作成とコマンドは ``maya/inhouse/hlib/docs/README.md`` を参照してください。
生成 HTML は ``maya/inhouse/hlib/docs/_build/html`` に出力し、Git には含めません。

参考: `Sphinx AutoAPI の公式ドキュメント <https://sphinx-autoapi.readthedocs.io/en/latest/>`_


maya.cmds と OpenMaya API 2.0 の使い分け
------------------------------------------

hlib 内部の実装では、``maya.cmds``(``cmds``)は **シーンに変化を与え、かつ
Undo 対応が必要な操作** に使用します(ノード・アトリビュート・接続の
作成/削除/設定、親子付け、選択変更、名前空間の作成/移動/削除など)。
これらは既存の ``@undo_chunk`` デコレータ(``hlib/decorators/undo.py``)や
``cmds.undoInfo`` の Undo チャンクに乗せる前提で cmds を使い続けます。

それ以外の **読み取り専用の照会** は ``maya.api.OpenMaya``(``om2``、
必要に応じて ``maya.api.OpenMayaAnim`` の ``oma2``)を直接使い、MEL コマンドの
文字列変換・往復コストを避けます。代表例:

- ``MSelectionList`` によるノード名解決・存在確認(``cmds.objExists`` の代替)
- ``MPlug`` の ``asDouble``/``asInt``/``asBool``/``asString``/``asMAngle``/
  ``asMDistance``/``asMTime`` 等によるアトリビュート値の取得
  (``plugs/plug.py`` の ``Plug.get()`` を参照。現実装の単一角度Plugは度、
  距離・時間は現在のUI単位。角度UI単位がradの場合はcmds.getAttrと異なる)
- ``MFnDependencyNode.getConnections()``/``MPlug.connectedTo()`` による接続の列挙
- ``MGlobal.getActiveSelectionList()`` による選択状態の取得。
  復元はUndo対応の ``cmds.select`` で行う（``preserved_selection`` を参照）。
- ``MNamespace`` による名前空間の存在確認・列挙(``namespaces/namespace.py``)
- ``MFnGeometryFilter.getOutputGeometry()`` による blendShape/cluster 等の
  デフォーマの出力ジオメトリ取得

一方で、``cmds.getClassification``、``cmds.aliasAttr``、
``cmds.editDisplayLayerMembers``、拘束・blendShape・skinCluster の
編集モード呼び出し(``cmds.blendShape(edit=True, ...)`` 等)のように、
**Maya API 2.0 に対応する API が存在しない MEL 専用コマンド** は、
読み取り専用であっても cmds のまま残します。無理に om2 で再実装せず、
対応する API が無いことを実装コメントか docstring に明記してください。

Mayaコマンド独自の判定をそのまま提供する処理も例外です。
``Node.history()`` は ``listHistory`` の構築履歴順、
``SkinCluster.unused_influences()`` は ``weightedInfluence`` の使用判定、
``Node.reset_attrs()`` は ``getAttr(settable=True)`` の書き込み可否を使用します。
APIのグラフ走査や個別フラグから似た判定を再構築して意味を変えないためです。

``Plug(node, mplug)`` が登録済みラッパー(``DoubleLinearPlug`` など)を選ぶための属性型名は、
``cmds.getAttr(<プラグ名>, type=True)`` と同じ文字列(``PlugRegistry`` のキー)を、
属性定義から om2 で求めます(``_core/attribute_type.py`` の ``attribute_type()``。
``MFnNumericAttribute.numericType()``、``MFnUnitAttribute``・enum・message・matrix の
apiType、``MFnTypedAttribute.attrType()``、API 2.0 に列挙値の無いデータ型は
``MFnAttribute.getAddAttrCmd()`` の型指定)。``cmds.getAttr(type=True)`` は使いません。
存在しない配列要素を問い合わせると要素を作る(blendShape の ``weight[i]`` では
``parentDirectory[i]`` なども作られる)、nurbsSurface の ``patchUVIds`` の存在しない要素で
Maya が異常終了する、mesh の内部属性(``edge[i]``・``face[i]`` など)で例外になる、
といった副作用と失敗を避けるためです。``attribute_type()`` は値を読まないため評価も
起こしません(例外は次の「値によって型が変わる属性」)。

- mesh の ``controlPoints`` は属性定義が ``double3`` でも ``cmds.getAttr(type=True)`` が
  ``float3`` を返すため、この属性だけ ``float3`` として扱います(nurbsCurve などは ``double3``)。
- 値によって型が変わる属性(generic 属性、任意のデータを受け付ける typed 属性、
  ``geometry`` 型)は、属性定義だけでは型名が決まらないため ``attribute_type()`` は
  ``None`` を返します。``Plug(node, mplug)`` は、generic 属性と任意のデータを受け付ける
  typed 属性(``MFnData.kAny``。``choice`` の ``input``/``output`` など)が行列を保持して
  いれば、``cmds.getAttr(type=True)`` と同じく ``matrix`` として ``MatrixPlug`` を選びます
  (``choice`` ノードで行列を切り替える構成など。``plugs/plug.py`` の ``_held_matrix_type()``)。
  保持する値の型は次の順に求め、評価はできるだけ避けます。

  1. 読み取りできない属性(``MFnAttribute.readable`` が偽。transform 系ノード共通の
     generic 属性 ``geometry`` など)と、存在しない要素は値を読みません。field 系ノードでは
     ``geometry`` の評価で ``falloffCurve[0]`` などの要素が作られるため、読むと
     ``Node(field).plugs()`` がシーンを変更してしまいます。
  2. 入力接続があれば、接続元の属性の型を使います(``choice.input[0]`` の接続元が
     ``worldMatrix[0]`` なら ``matrix``)。接続元の型が属性定義で決まる場合は値を読まず、
     上流の評価を起こしません。接続元も値によって型が変わる属性なら、接続元に同じ規則を
     適用して辿ります。辿った先で入力接続の無い接続元は値を読むため、上流の評価が起こります
     (``choice2.input[0]`` ← ``choice1.output`` では ``choice1`` を、``choice.input[0]`` ←
     ``unitConversion.output`` では ``unitConversion`` を評価します)。
  3. 入力接続が無ければ値を読みます。ノードが計算する出力(``choice.output`` など)は
     ``cmds.getAttr(type=True)`` と同じく評価(compute)が起こります。評価によって
     ワールド空間の出力の要素が作られる場合もあります(インスタンス化されたシェイプの
     2つ目のインスタンスを拘束元にした geometryConstraint の ``constraintGeometry`` では、
     シェイプの ``worldMesh[0]`` が作られます。``cmds.getAttr(type=True)`` でも同じです)。

  ``double3`` などの数値の組を保持する場合は子を持たず ``Double3Plug`` で扱えないため、
  基底の ``Plug`` のままにします(``get()`` は tuple)。``geometry`` 型の typed 属性
  (デフォーマの ``inputGeometry`` など)は対象外で、値を読みません。
- Maya 内部のデータ型(``cmds.addAttr`` で作成できない ``nurbsPatchUVIds``・``polyFaces``
  など。``is_internal_data_type()``)の存在しない配列要素は、値を読むと Maya が異常終了する
  場合があるため、``Plug.get()`` と ``ArrayPlug.element(create=True)`` が ``RuntimeError`` に
  します(maya.cmds・MPlug のどちらでも値を読みません)。
- 既存のプラグについて ``cmds.getAttr(type=True)`` と一致することを
  ``test_cmds_parity.py`` で検証しています(2022・2027 で全ノード型の既存プラグを
  突き合わせた確認では、値によって型が変わる属性以外はすべて一致)。テストでは
  存在しない配列要素へ ``cmds.getAttr(type=True)`` を使いません(要素が作られ、
  Maya が異常終了する属性もあるため)。

そのため Plug の生成は、値によって型が変わる属性で値を読む場合(上記の評価と、評価による
ワールド空間の出力の要素の作成)を除き、シーンを変更しません。要素の作成が必要な処理は
``ArrayPlug.element(index, create=True)`` のように明示します。所有ノードが削除済み、
または動的属性が ``deleteAttr`` で削除済みの場合は、Plug の生成を ``RuntimeError`` にし、
既存の Plug も無効(``Plug.is_valid()`` が ``False``。``str()``・``name()`` は空文字列、
値の取得・設定と、属性の情報・接続の問い合わせは ``RuntimeError``)として扱います。
削除済みの属性の MPlug で値を読み書きすると Maya が異常終了し、削除済みノードの MPlug は
古い値を返し、Undo の対象から外れた削除済みノードの MPlug は名前の問い合わせでも
Maya を異常終了させるためです。動的属性の削除は Undo のために属性の MObject が保持され
``MObjectHandle.isValid()`` では判定できないため、所有ノードの
``MFnDependencyNode.attributeClass()`` がその属性を ``kInvalidAttr`` (ノードに無い属性)と
返すかも確かめます(静的属性はノードが有効な間は常に存在するため確かめません)。
生の ``om2.MPlug`` を受け取る変換(``_core.coerce`` の ``_mplug_name()``)も
``mplug_attribute_exists()`` で同じ判定を行い、削除済みの属性は ``ValueError`` にします。
MPlug・Plug を所有ノードへ解決する処理(``nodes/node.py`` の ``_resolve_node()`` と
``_core.coerce.to_node()``)も、所有ノードが有効で属性だけが削除されている場合は
``DeletedAttributeError`` (``ValueError`` と ``RuntimeError`` の両方の派生)にします。
所有ノードへ解決すると削除済みの対象を黙って受け付けてしまうためで、``RuntimeError`` の
派生にするのは、解決できない対象をすべて ``RuntimeError`` にする ``Node(...)`` の規則を
保つためです。
``Plug(node, mplug)`` は ``MPlug.node()`` と ``node`` の MObject を比べ、所有ノードではない
``node`` を渡す誤用を静的属性・動的属性とも ``RuntimeError`` にします(静的属性は同じ型の
別ノードにも存在し、``attributeClass()`` では検出できないため)。
ただし Undo の対象から外れて削除されたノードの MPlug は ``MPlug.node()`` の時点で
Maya が異常終了し、API では検出できません。hlib の内部でも MPlug を削除操作をまたいで
保持せず、Plug(ノードの ``MObjectHandle`` を持つ)を保持してください。

``Node(...)`` は入力の解決(名前の検索など)を ``__new__`` で1回だけ行い、結果を
``__init__`` へ引き継ぎます。ラッパー型の選択のために解決をやり直さないでください
(``Node`` の生成はシーン全体の列挙などで大量に呼ばれるため)。

大量に呼ばれる処理の性能について、次を前提にしています(Maya 2022・2027 で transform と
network を各 2000 個作成した実測。比較の基準は ``maya.cmds`` へ ``cmds.getAttr(type=True)`` で
型を問い合わせていた以前の実装。倍率は実行ごと・Maya のバージョンごとに変動するため範囲で示します)。

- ``Node(...)``・``node.plug()``・``hlib.ls()`` は以前の実装の約 0.3〜0.6 倍の時間です
  (``Node(...)`` は約 0.3〜0.4 倍、``node.plug()`` は transform の ``tx`` で約 0.3〜0.5 倍、
  DG ノードの動的属性で約 0.4〜0.6 倍)。``Plug(node, mplug)`` の所有ノードの確認
  (``MPlug.node()`` との比較)を含みます。例外として、``Node(MPlug)``・``hlib.node(MPlug)``・
  ``to_node(MPlug)`` のように生の ``MPlug`` から所有ノードを解決する経路は、削除済み属性の
  確認が加わるため以前の約 1.4 倍です(1 回あたり約 +1.4µs)。hlib 内部の頻繁な処理は
  ``Node(mplug.node())`` (MObject)を使うため影響しません。
- ``Plug.get()`` は読み方(``MPlug.asDouble`` など)を属性定義から Plug ごとに一度だけ選んで
  保持するため、以前の約 0.4〜0.65 倍です(transform の ``tx`` は約 0.5〜0.65 倍、DG ノードの
  動的属性は約 0.4〜0.5 倍)。値を読むたびに行う有効性の確認(動的属性は
  ``attributeClass()``)はこの中に含まれます。
- ``str(plug)``/``Plug.full_name()`` は、DAG ノードの Plug で以前の約 2〜2.6 倍
  (1 回あたり約 +1µs)です。以前は ``MPlug.name()`` をそのまま返していたため、同じ短い
  名前のノードがあると曖昧な名前になっていました。一意な名前を返すために
  ``MFnDependencyNode.hasUniqueName()`` を毎回問い合わせる必要があり(名前の一意性は
  ほかのノードの作成・名前変更で変わるため、結果を保持できません)、この分は削れません。
  DG ノードは一意性の確認が不要なため、静的属性で約 1.2 倍、属性の存在確認
  (``attributeClass()``)が加わる動的属性で約 1.2〜1.6 倍です。名前を繰り返し使うループでは、
  ``str(plug)`` を一度だけ求めて使い回すか、``plug.mplug()`` を直接使ってください。
  判定の処理(``_require_valid()``・``full_name()`` の属性の存在確認)は呼び出しの負荷を
  避けるため ``_attribute_exists()`` と同じ内容を直接書いています。変更する場合は3か所を
  そろえてください。

変換の際は必ず ``cmds`` ベースの旧実装と ``om2`` ベースの新実装を
同一ノードで比較するスクリプトを Maya 上で実行し、値の一致(特に単位変換と、
周期 NURBS カーブの CV アドレッシングのような cmds 固有の挙動)を確認してから
置き換えてください。

一度限りの手動確認で終わらせず、将来の Maya バージョン変更やリファクタによる
回帰を継続的に検知するため、``hlib/__tests__/test_cmds_parity.py`` に
「hlib の戻り値と ``cmds`` の生の値を同一テスト内で突き合わせる」形の
テストを追加してください。新しく cmds→om2 の置き換えを行った場合は、
対応する突き合わせをこのファイルに追加するのが規約です
(既に他ファイルでカバー済みの突き合わせの一覧は同ファイルの
docstring を参照)。


maya.cmds へ渡す名前と入力の正規化
----------------------------------

利用者向けの仕様は :doc:`cmds_interop` にまとめています。hlib の実装では次を守ります。

- maya.cmds へ渡すプラグ名は ``Plug.full_name()``、または ``_core.coerce`` の
  ``plug_path()``/``unique_node_name()``/``to_name()`` で作ります。``MPlug.name()`` と
  ``MFnDependencyNode.name()`` は短いノード名しか含まず、同じ短い名前のノード
  (``grp1|dup`` と ``grp2|dup``)があると曖昧になるため、maya.cmds へ渡したり
  重複判定のキーにしたりしません。例外は ``Plug.full_name()`` の高速経路で、短い名前が
  一意なノード(DG ノードと、``hasUniqueName()`` が真でインスタンス化されていない
  アンダーワールド以外の DAG ノード)に限り ``MPlug.name()`` をそのまま返します(このとき ``MPlug.name()`` は
  ``<最短一意名>.<属性パス>`` と一致します。``str(plug)`` は大量に呼ばれるため)。
- ノード・属性を受け取るコマンドとメソッドは、``_core.coerce`` の ``to_name``/``to_names``
  (名前)、``to_node`` (ノード。Plug は所有ノード、Component は所有シェイプ)、
  ``to_node_name`` (``parent`` などノードが必要な単一の引数。所有ノードの完全パス)、
  ``to_plug`` (属性)で入力を正規化します。``to_name``/``to_names`` は文字列を解決せずに
  そのまま渡します。例外は、対応しない型が ``TypeError``、空・削除済みの対象が
  ``ValueError``、解決できない(存在しない・一意でない)文字列が ``RuntimeError`` です。
  ただし ``to_node`` は削除済みの Node と、所有ノードが削除済みの Plug・Component を
  そのまま(無効な所有ノードとして)返し、有効性の扱いは呼び出し側の API に任せます
  (``Node(...)``/``hlib.node`` と ``hlib.constraint``/``Transform.add_constraint`` は
  従来どおり ``RuntimeError``、``Node.is_parent_of`` などの判定は ``False``)。所有ノードが
  有効で属性だけが削除された Plug・MPlug は、返す Node で削除を表せないため ``to_node`` でも
  ``DeletedAttributeError`` (``ValueError``。``RuntimeError`` の派生でもある)です。
- ``MSelectionList`` の属性の要素は ``getDagPath()`` を使えず、インスタンスの情報も
  持たないため、所有ノードは ``_core.coerce.selection_owner()`` で求めます(元の文字列の
  ノード部分から、名前が指すインスタンスを保持します)。
- ``Components`` を maya.cmds へ渡すときは ``compact_names()`` で連続する番号を範囲指定に
  まとめ、全番号の検証もコレクションごとに1回だけ行います。
- Node・Plug など単一の対象を表すクラスに ``__len__``/``__iter__`` を追加しません。
  maya.cmds がシーケンスとして展開してしまうためです。``__getitem__`` を持つ
  ``ArrayPlug`` は同じ理由で maya.cmds へそのまま渡せないため、docstring と
  :doc:`cmds_interop` に明記しています。
- 仕様の検証は ``__tests__/test_cmds_interop.py`` (maya.cmds との受け渡し)と
  ``__tests__/test_coerce.py`` (正規化の規則)に追加します。

hlib内で独自プラグインを作らない方針
------------------------------------

hlib は ``MFnPlugin`` によるコマンド登録・ノード登録など、Maya 起動時に
別途ロードが必要な**独自プラグインを一切同梱しません**。機能追加の際、
「cmds/om2 だけでは実現できないので専用プラグインを作る」という選択肢は
取らないでください。

これは実際に、Maya 2022 の ``playbackOptions`` がUndo履歴を作らない制限を
補うため、``_core/_playback_range_command.py`` に専用の ``MPxCommand``
(``hlibSetPlaybackRange``)を実装していたことがありましたが、以下の理由で
撤去し、この方針として明文化しました。

- プラグインは初回ロード時に Maya の「信頼されていない場所からのロード」
  セキュリティ警告を発生させ、GUI操作(手動でのダイアログ承認)を要求する。
  VS Code からの送信実行やバッチ処理を止めてしまう。
- プラグインの登録・解除、``.mod`` や検索パスとの整合性など、hlib 本体とは
  別種の保守コストが増える。
- 対象の制限はMayaネイティブの既知の挙動であり、cmds/om2の使い分け方針
  (前節参照)の範囲内で吸収できないものは、無理に回避せず制限として
  docstring に明記するに留める(``TimeSlider.set_playback_range`` の
  Maya 2022 に関する記載を参照)。

「Undo対応にしたいが cmds/om2 だけでは足りない」という要求が出た場合も、
専用プラグインの新規作成ではなく、既存の ``undo_chunk``/``undo_transaction``
(前節参照)で表現できないか、または対象操作自体をMayaの制限として
受け入れて文書化できないかを先に検討してください。

コンポーネントの構成
--------------------

``components/component.py`` の ``Component`` / ``Components`` は、
単体のシェイプ・番号の参照と、同一シェイプの要素群を担当します。
``components/point_component.py`` の ``PointComponent`` / ``PointComponents`` は、
XYZ 座標の取得・設定と一括ミラーを担当します。

``vertex.py``、``cv.py``、``edge.py``、``face.py``、``uv.py`` には、
それぞれ単体型と複数形をまとめます。Vertex / CV は PointComponent、
Vertices / CVs は PointComponents を継承します。
Edge / Face / UV は Component、Edges / Faces / UVs は Components を継承します。
基底クラスは ``hlib.components`` から import できます。


コマンドの追加
--------------

``cmds/<コマンド名>.py`` に同名の関数を定義すると、実行時に自動で公開されます。
実行時の公開に ``cmds/__init__.py`` の編集は不要です。追加・変更・削除後は ``hlib.reload()``
で反映します。エディターの静的解析(Pylance)は動的公開を追跡できないため、
``hlib/__init__.py`` と ``cmds/__init__.py`` の ``if TYPE_CHECKING:`` ブロックにも
同名の import を追記してください。追記漏れは ``test_typing_exports.py`` が検出します。非公開名（先頭が ``_``）、サブパッケージ、同名関数を持たない
ファイル、他モジュールから取り込んだ関数は公開対象外です。利用時は
``hlib.<コマンド名>(...)`` として呼び出します。
モジュールの docstring に Synopsis、Return value、Related commands、Flags、
Examples を記述すると、コマンド専用テンプレートで個別ページを生成します。

Maya に対応するコマンドの関数名・ファイル名は Maya と同じキャメルケースに
揃えます。例: ``createNode.py`` の ``createNode()``。独自のクラスメソッドはsnake_caseにします。


nodes のファイル名
-------------------

``nodes/*.py`` のうち、``@node_wrapper("<nodeType>")`` で単一の Maya nodeType に
1:1 対応するファイルは、``cmds/`` と同じ方針でその nodeType 文字列と同じ
キャメルケースをファイル名に使います。例: ``@node_wrapper("nurbsCurve")`` の
``NurbsCurve`` は ``nodes/nurbsCurve.py``。単語が1つの nodeType（``transform``、
``joint``、``mesh``、``camera`` など）は元々小文字1語なので、ファイル名は
変わりません。

対応する Maya nodeType が無いファイル（``node.py``、``shape.py`` など、型文字列
ではなく実行時のノード種別で判定するもの）はこの対象外で、従来どおり
snake_case のままです。

``Constraint`` 系は1クラス1ファイルに分割しています。共通基底 ``Constraint``
（nodeType を持たない）は ``constraint.py`` に残し、``ParentConstraint`` 〜
``PointOnPolyConstraint`` の10種類はそれぞれ対応する nodeType 名のファイル
（``parentConstraint.py``、``pointConstraint.py`` など）に1クラスずつ定義します。

plugs のファイル名
-------------------

``plugs/*.py`` は nodes とは異なり、``@plug_wrapper("<attrType>")`` で Maya
attrType に 1:1 対応するファイルも含めて snake_case に統一します
（``bool_plug.py``、``double_linear_plug.py``、``double3_plug.py``、
``matrix_plug.py``）。``_plug`` は Maya 由来ではなく hlib 側で付与する接尾辞
のため、attrType 部分だけをキャメルケースにすると
``doubleLinear`` + ``_plug`` のように表記が混在してしまうことを避けています。

maths のファイル名
-------------------

``cmds`` はMayaに合わせたcamelCase、``nodes`` はMaya nodeTypeと同名にします。
それ以外のモジュールはsnake_case、クラスはPascalCase、独自メソッドはsnake_caseです。
例えば ``EulerRotation`` は ``maths/euler_rotation.py``、``ChannelBox`` は
``editors/channel_box.py`` に置きます。移動の値型は ``Translation``、
回転の値型は回転順序を持つ ``EulerRotation`` に統一しています。

Mayaの現在値を照会するAPIはメソッド、保持するデータはプロパティまたはフィールドにします。
詳しい移行先は :doc:`api_naming` を参照してください。


公開 API の配置
---------------

クラスは所属するサブパッケージから利用します。
``hlib.nodes.Node``、``hlib.plugs.Plug``、``hlib.components.Vertex``、
``hlib.files.Scene``、``hlib.maths.Matrix`` のように
所属するパッケージから利用します。``hlib.reload()`` は再読み込みの入口です。
``hlib.Node`` は利用できません。
コマンドの実装は ``cmds`` に配置し、自動検出後に hlib 直下にも公開されます。
利用者向けの構文・使用例は ``hlib.createNode()`` や ``hlib.ls()`` に統一します。
``hlib.ls`` と ``hlib.cmds.ls`` は同じ関数です。追加・変更・削除は
``hlib.reload()`` で両方に反映されます。既存の公開名（``reload`` や
サブパッケージ名）と衝突するコマンドは ``hlib.cmds`` 側だけで利用できます。


内部実装
--------

``hlib._core`` は型登録・検出・初期化・再読み込みを担当する内部パッケージです。
通常のツールからはアクセスせず、コマンド、各クラス、``hlib.reload()`` を利用します。
外部拡張では ``hlib.extensions.node_wrapper`` / ``plug_wrapper`` を利用できます。
拡張の配置・依存確認・自動登録は :doc:`extensions` を参照してください。
``collection_export`` は内部APIです。
hlib 内にラッパーを追加する際は、既存実装と同じく
``from .._core.registry import node_wrapper`` などを使用します。
旧パス ``hlib.core`` は廃止しました。
