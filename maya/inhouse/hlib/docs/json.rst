JSONで状態を一時保存する
============================

``hlib.json`` はhlibの数学型、Mayaの参照、取得時点の状態をJSONへ保存します。
``load()`` はデータを読むだけで、シーンや選択を変更しません。
状態を反映するときだけ ``Snapshot.apply()`` を呼び出します。

基本的な使い方
----------------

.. code-block:: python

    import hlib

    saved = hlib.json.capture(hlib.ls(sl=True), kind="pose")
    path = hlib.json.dump(saved)
    print(path)  # OSの一時フォルダー内の一意な.json

    restored = hlib.json.load(path)
    plan = restored.plan()
    print(plan.changes)
    print(plan.errors)
    plan.apply()  # 最新の状態で再検証してから適用

パスを省略すると一時ファイルを作ります。自動削除しないため、不要になったら
返された ``Path`` の ``unlink()`` を呼び出してください。
明示パスへ保存する場合は、親フォルダーを事前に作成してください。
保存はUTF-8です。保存先と同じフォルダーへ一時ファイルを書き、置換します。
JSON変換や置換に失敗した場合、既存ファイルを成功したものとして扱いません。

.. code-block:: python

    from hlib.maths import Vector, EulerRotation

    path = hlib.json.dump({
        "description": "調整前",
        "position": Vector(1, 2, 3),
        "rotation": EulerRotation(0.1, 0.2, 0.3, "zyx"),
        "target": hlib.node("control"),
    }, metadata={"label": "backup"})

    data = hlib.json.load(path)
    node = data["target"].resolve()
    document = hlib.json.load_document(path)
    print(document.metadata)

通常のdictはdict、Snapshotは用途別Snapshotとして戻ります。
Node・Plug・Componentは生きたラッパーではなく、未解決の参照データに戻ります。
``resolve()`` するまでは対象がシーンに存在する必要はありません。
SelectionとComponentsを通常の値として保存した場合は、参照の順序付きリストへ戻ります。
選択自体を復元する用途には ``kind="selection"`` を使用してください。

対応する状態
----------------

.. list-table::
   :header-rows: 1

   * - kind
     - 対象
     - 保存・適用範囲
   * - selection
     - 対象列。省略で現在選択
     - 順序付きのノード・属性・コンポーネント選択
   * - attributes
     - Nodeまたはその列
     - attributesで明示した属性の型と値
   * - pose
     - Transformまたはその列
     - ローカルTRS、shear、回転順序、pivot、rotateAxis、offsetParentMatrix。JointはjointOrient等も含む
   * - curve
     - NurbsCurveまたはTransform、その列
     - 複数ShapeのCV位置・override色・線幅。同じ次数・ノット・form・CVウェイトのみ適用
   * - skin_weights
     - SkinClusterまたはその列
     - 先頭meshの全influenceウェイト、blendWeights、スキニング関連設定
   * - animation
     - AnimCurveまたはその列
     - 全8型のキー、接線、weighted、ロック、前後Infinity
   * - driven_keys
     - 駆動先Nodeまたはその列
     - 上流SDKカーブとblendWeighted・unitConversionの値。既存接続を照合
   * - editor
     - Viewport、Outliner、TimeSliderまたはその列
     - 公開表示設定、タイムライン時刻・再生範囲・アニメーション範囲

.. code-block:: python

    attrs = hlib.json.capture(
        hlib.node("control"), kind="attributes",
        attributes=["translate", "visibility", "customValue"],
    )
    selection = hlib.json.capture(kind="selection")
    curves = hlib.json.capture(hlib.node("control"), kind="curve")
    timeline = hlib.json.capture(hlib.timeSlider(), kind="editor")

属性は数値・enum・文字列・行列・数値2/3要素compoundに対応します。
配列は要素を明示してください。任意のtyped arrayやカスタムデータ型は対象外です。
属性のロック・入力接続・表示設定を勝手に解除しません。

別の対象へ適用する
--------------------

.. code-block:: python

    saved = hlib.json.capture(hlib.node("characterA:control"), kind="pose")
    plan = saved.plan(namespace_map={"characterA": "characterB"})
    if not plan.errors:
        plan.apply()

    # 保存時の絶対名をキーに、対象を個別指定することも可能
    source = saved.records[0]["node"].path
    saved.apply(mapping={source: "anotherControl"})

明示対応を優先し、その次に名前空間変換を使います。
どちらも指定しない場合はUUID、その後に保存名で解決します。
候補が複数ある場合、型が異なる場合、不明な場合はエラーにします。
エディターのmappingはUI名同士の対応です。

検証とUndo
----------------

``validate().valid`` と ``validate().errors`` で適用可能性を確認できます。
``plan()`` では対象と変更前後を取得できます。``apply()`` は毎回再検証します。
取得時の距離・角度・時間単位と現在の単位が違う場合は適用を拒否し、
自動で単位を変更・変換しません。選択Snapshotにはこの制限はありません。

適用にはUndoが有効である必要があります。シーンの編集は一回のUndoにまとめます。
途中でMaya側の例外が起きた場合は例外を通知します。シーンの途中変更を自動で
巻き戻すトランザクションではありません。必要に応じて一回Undoしてください。
エディター設定は専用の内部PythonコマンドでUndo/Redoします。
UIを削除した後はそのUIの設定をUndoで復元できません。

制限とデータ形式
------------------

* 既存対象の更新用です。ノード・Shape・skinCluster・SDK接続の新規作成は行いません。
* ポーズはローカル属性値の復元です。親の異なるリグへのワールド空間リターゲット、ブレンド、ミラーは行いません。
* ロック済み・参照ファイル由来の更新対象は適用前に拒否します。
* カーブのconstruction history付きShapeは拒否します。形状の再構築・CV数変更は行いません。
* スキンはトポロジーの接続情報とinfluence集合が一致する場合に限ります。疎ウェイトの省略部分はゼロです。
* アニメーションは保存キー集合へ置換します。空の保存カーブを非空カーブへ適用する操作は、最後のキー削除によるノード消失を避けるため拒否します。
* SDKは既存の接続構成が一致する場合だけ更新します。別のグラフを作り直す機能ではありません。
* コンポーネント参照は番号です。選択Snapshotはトポロジー変更後の同一頂点を保証しません。UVは現在のUVセットの一致も検証します。
* エディターは画面配置、カメラ、Channel Box選択、再生状態、タイムスライダーのドラッグ選択範囲を含みません。

JSON全体は ``format="hlib.json"``、``version=1`` を持ち、Snapshotにも版を持たせています。
数学型は型名を保持し、EulerRotationはラジアンと回転順序、Matrixは行優先16要素です。
dict自体も型タグで包むため、利用者の ``type`` キーなどと衝突しません。
非有限値、未対応型、文字列以外のdictキー、重複JSONキー、未対応形式は拒否します。
任意クラスのimport、pickle、コード実行は行いません。
既存の ``SkinCluster.dump_weights()/load_weights()`` の形式とは別形式です。
旧形式の自動移行や、外部ツール形式の直接読み込みは行いません。
