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
     - Vector、Matrix、Quaternion などの数学型（Matrix 以外は frozen dataclass）
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
     - 型登録、ラッパー検出、初期化、再読み込み、Node/文字列入力の正規化(coerce)の内部基盤

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

クラスごとに独立したページを生成し、cymel の API リファレンスに合わせて
``Methods:`` にメソッド名・シグネチャ・概要の一覧、``Methods Details:`` に
各メソッドの詳細をアルファベット順で掲載します。
一覧では省略可能な引数を角括弧で、詳細では既定値付きで表示します。
属性は ``Attributes:`` に掲載します。
引数・戻り値・戻り値の型は docstring から生成し、API 名は実装に従います。
表記用テンプレートは ``_templates/autoapi/python/class.rst`` で管理し、
配色やナビゲーションは Sphinxdoc テーマと ``_static/custom.css`` を使用します。

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

``cmds/<コマンド名>.py`` に同名の関数を定義すると、自動で公開されます。
``cmds/__init__.py`` の編集は不要です。追加・変更・削除後は ``hlib.reload()``
で反映します。非公開名（先頭が ``_``）、サブパッケージ、同名関数を持たない
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
