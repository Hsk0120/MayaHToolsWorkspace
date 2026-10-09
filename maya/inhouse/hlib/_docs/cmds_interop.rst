maya.cmds との受け渡し
============================================================

hlib のオブジェクトと ``maya.cmds`` を組み合わせて使うときの正式な仕様です。
hlib のNodeや単一値Plugは ``maya.cmds`` へそのまま渡せます。配列・複合Plugは
``str(plug)`` または ``plug.fullName()`` を渡してください。また hlib のコマンドは、
文字列の名前に加えて hlib と Maya API 2.0(``om2``)のオブジェクトを受け付けます。

例は Maya の Script Editor で実行します。既存ノード名は使用するシーンに合わせてください。
最初に ``import hlib`` を実行してください。

maya.cmds へそのまま渡せるもの
------------------------------------------------------------

``maya.cmds`` は文字列以外の引数に ``str()`` を適用し、リストのように
``len()`` と ``[]`` を持つオブジェクトは要素ごとに展開します。hlib のオブジェクトは
``str()`` で maya.cmds が一意に解決できる名前を返すため、そのまま渡せます。

.. list-table::
   :header-rows: 1
   :widths: 30 45 25

   * - オブジェクト
     - ``str()`` の結果
     - 例
   * - ``Node``
     - 最短一意名(``Node.name()``)。同じ短い名前のノードがあればパスを含む
     - ``grp1|dup``、``ns:ctrl``
   * - ``Plug`` （配列・複合を除く）
     - ``<ノードの最短一意名>.<アトリビュートパス>`` (``Plug.fullName()``)
     - ``grp1|dup.translateX``、``cubeShape.pnts[2].pntx``
   * - ``Component`` (``Vertex`` など単体)
     - シェイプの完全パス、種類、番号(``Component.fullName()``)
     - ``|cube|cubeShape.vtx[3]``
   * - ``Vertices`` などの複数形、``Selection``、``Joints`` などのコレクション
     - 各要素の名前に展開される
     - ``cmds.select(vertices)``

.. code-block:: python

   import maya.cmds as cmds
   import hlib
   from maya import cmds
   from hlib.components import Vertex

   grp1 = hlib.createNode("transform", name="grp1")
   grp2 = hlib.createNode("transform", name="grp2")
   dup1 = hlib.createNode("transform", name="dup", parent=grp1)
   dup2 = hlib.createNode("transform", name="dup", parent=grp2)

   plug = dup1.plug("tx")
   print(plug)                     # grp1|dup.translateX
   cmds.setAttr(plug, 3.0)
   print(cmds.getAttr(plug))       # 3.0（grp2|dup は変更されない）
   cmds.connectAttr(dup1.plug("ty"), dup2.plug("ty"))

   cube = hlib.node(cmds.polyCube(name="cube")[0])
   vertex = Vertex(cube.shape(), 3)
   cmds.select([dup1, vertex])     # Node と Component をまとめて選択
   cmds.xform(vertex, translation=(0, 1, 0), worldSpace=True)

名前の規則は次のとおりです。

- 名前は ``str()`` を呼ぶたびに現在のシーンから求めます。名前変更や親子付け替えの後も、
  同じオブジェクトをそのまま渡せます。
- 同じ短い名前のノード(``grp1|dup`` と ``grp2|dup``)があっても、区別できるパスを
  含むため曖昧になりません。``Node.fullName()`` は常に完全な DAG パスを返します。
- Plug のアトリビュートパスはロング名です。必要な配列インデックス(``worldMatrix[0]``、
  ``pnts[2].pntx``)を含み、エイリアスがあればエイリアス名を使います。
  インスタンスごとのアトリビュート(``worldMatrix`` など)は、インデックスがインスタンス番号を表します。
- 削除済みのノードとその Plug、``deleteAttr`` で削除された動的アトリビュートの Plug は空文字列に
  なります(``Plug.valid()`` が ``False``。``plug.name()`` も空文字列)。これらの Plug の
  ``get()``/``set()`` は削除前の古い値を返したり Maya を異常終了させたりせず
  ``RuntimeError`` になります。アトリビュートの情報(``attribute()``・``locked()``・``default()``
  など)と接続(``source()``・``connectTo()`` など)の問い合わせも ``RuntimeError`` です
  (Undo の対象から外れた削除済みノードの MPlug は、名前の問い合わせでも Maya を
  異常終了させるためです)。構造の判定(``array()``・``compound()``・
  ``isElement()``・``child()``)だけは例外になりません。
  同じ名前でアトリビュートを追加し直しても、古い Plug は別のアトリビュートとして無効のままです(Undo で削除を
  取り消した場合は再び有効になります)。削除済みのシェイプの Component は ``str()`` で
  例外になります。
- インスタンス化されたノードの Node は、指定されたインスタンスのパスを保持します
  (``hlib.node(<2つ目のインスタンスのパス>)``)。そのインスタンスだけが削除された場合は、
  パスを使う操作はRuntimeErrorになります。別インスタンスへは切り替えません。
- インスタンスごとのアトリビュート(``worldMatrix`` など)は、インスタンス化された祖先による
  間接インスタンスも含め、インスタンス番号の要素を評価前から存在する要素として扱います
  (``elements()``・``get()``・``array_plug[1]``)。``Transform.matrix(ws=True)`` は
  ラッパーが保持するインスタンスの要素(``worldMatrix[<インスタンス番号>]``)を使います。
- ``om2.MDagPath`` の ``str()`` も最短一意パスなので渡せます。
- Plug を作る・取得する操作(``node.plug()``、``node.plugs()``、``Plug._resolve_input()``、
  ``Selection([...])`` など)は、原則としてシーンを変更しません。アトリビュート型はアトリビュート定義から求め、
  maya.cmds へ問い合わせないためです(評価も起こしません)。例外は次の項目の
  「値によって型が変わるアトリビュート」で、値を読むためノードが計算する出力の評価(compute)が起こり、
  評価によってシーンの状態が変わる場合があります。たとえばインスタンス化されたシェイプの
  2つ目のインスタンスを拘束元にした geometryConstraint では、``constraintGeometry`` の
  Plug を作る(``node.plugs()`` の結果に含まれる場合を含む)と、評価によってシェイプの
  ``worldMesh[0]`` が作られます(``cmds.getAttr(type=True)`` でも同じです)。
  存在しない配列要素(``input1D[10]``)の Plug を作っても要素は
  作られません(mesh の ``controlPoints[i]`` の Plug を作っても ``pnts[i]`` は作られず、
  blendShape の ``weight[5]`` の Plug を作っても ``parentDirectory[5]`` などは作られません)。
  maya.cmds では例外や異常終了になる mesh の内部アトリビュート(``edge[1]`` など)や nurbsSurface の
  ``patchUVIds`` の要素も、Plug として扱えます。要素を作るには
  ``array_plug[10].set(value)`` のように値を設定するか、その参照へ接続します。
  ただし ``patchUVIds`` のような Maya 内部のデータ型の配列では、存在しない要素の
  ``get()`` と ``element(i, create=True)``/``addElement()`` は ``RuntimeError`` です
  (maya.cmds でも MPlug でも、値を読むと Maya が異常終了する場合があるためです)。
- 値によって型が変わるアトリビュート(``choice`` の ``input``/``output`` のような任意のデータを
  受け付けるアトリビュートと、``unitConversion`` の ``input``/``output`` のような generic アトリビュート)は、
  保持する値が行列なら ``cmds.getAttr(type=True)`` と同じく ``matrix`` として
  ``MatrixPlug`` になります(``get()`` は ``Matrix``)。保持する値の型は次の順に求めます。

  - 読み取りできないアトリビュート(transform 系ノード共通の ``geometry`` など)と、存在しない
    要素は値を読みません(基底の ``Plug`` になります)。
  - 入力接続があれば、接続元のアトリビュートの型を使います(``choice.input[0]`` の接続元が
    ``worldMatrix[0]`` なら ``MatrixPlug``)。接続元の型がアトリビュート定義で決まる場合は値を読まず、
    上流の評価も起こりません。接続元も値によって型が変わるアトリビュート(``choice`` の ``output``、
    ``unitConversion`` の ``output`` など)の場合は、接続元に同じ規則を適用して辿ります。
    辿った先の接続元に入力接続が無ければその値を読むため、上流の評価が起こります
    (``choice2.input[0]`` の接続元が ``choice1.output`` なら ``choice1`` を、
    ``choice.input[0]`` の接続元が ``unitConversion.output`` なら ``unitConversion`` を評価します)。
  - 入力接続が無ければ、Plug の作成時に値を読みます。ノードが計算する出力
    (``choice.output`` など)では ``cmds.getAttr(type=True)`` と同じく評価(compute)が
    起こります(``node.plugs()`` や ``plug.destinationsWithConversions()`` の結果に含まれる場合も同じです)。

  ``double3`` などの数値の組を保持する場合は基底の ``Plug`` で、``get()`` は tuple です
  (generic アトリビュートは子を持たないため ``Double3Plug`` では扱えません)。型は Plug の作成時に
  決まるため、``choice`` の ``selector`` を切り替えて行列以外を出力させた後の
  ``MatrixPlug.get()`` は ``RuntimeError`` です(Plug を作り直してください)。
- ``node.plug()`` はアトリビュート名(ロング名・ショート名・エイリアス)に加えて、``str(plug)`` の
  アトリビュート部分と同じアトリビュートパス(``input1D[3]``、``worldMatrix[0]``、``pnts[2].pntx``、
  ``inputTarget[0].inputTargetGroup[7].inputTargetItem[6000].inputComponentsTarget``)を
  受け付けます。配列要素の番号を含まない配列複合アトリビュートの子(``input3Dx``、blendShape の
  ``inputTargetGroup`` のような子の配列を含む)は、maya.cmds で解決できないため
  ``RuntimeError`` です(``input3D[0].input3Dx``、``inputTarget[0].inputTargetGroup`` の
  ように指定します)。``node.plugs()`` の結果にもこれらは含まれません。
  ``node.input3Dx`` のような Python のアトリビュートアクセスでは、``hasattr``/``getattr(node, name, default)``
  が使えるよう ``AttributeError`` になります。
  配列インデックスは 0〜2147483647(``MPlug.logicalIndex()`` の範囲)です。範囲外の番号
  (``input1D[4294967296]`` など)は ``node.plug()`` では ``AttributeError``、
  ``array_plug.element()``/``array_plug[i]`` では ``IndexError`` で、別の要素へ読み替えません
  (``MPlug.elementByLogicalIndex()`` は ``input1D[0]`` へ変換します)。なお名前の文字列
  (``Plug._resolve_input("pma.input1D[4294967296]")``、``cmds.getAttr`` など)は、maya.cmds と同じく
  2147483647 番の要素として解決されます。
  ``message`` 型のように値を持たないアトリビュートの配列では要素を作成できず、接続した時点で
  要素ができます(``addElement()`` は接続するまで同じ番号を返します)。
- ``createNode("mesh")`` で作っただけの ``inMesh`` が未接続の空の mesh の ``uvpt[i]`` や、
  空の subdiv の ``controlPoints[i]``・``weights[i]`` の存在しない要素では、``get()`` と
  ``element(i, create=True)``/``addElement()`` が ``cmds.getAttr`` と同じく Maya を異常終了
  させる場合があります(形状を持つノードでは起こりません)。形状を接続してから扱ってください。
- 削除済みノードの Plug から、要素・子・親などの新しい Plug は取得できません
  (``RuntimeError``)。削除済みノードの名前で問い合わせると、同じ名前で作り直された
  別のノードを変更してしまうためです。Undo でノードが戻れば、再び取得できます。

そのまま渡せないもの
------------------------------------------------------------

.. list-table::
   :header-rows: 1
   :widths: 25 40 35

   * - オブジェクト
     - 理由
     - 代わりに渡すもの
   * - ``ArrayPlug``・``CompoundPlug`` 自体（Double3Plug等を含む）
     - ``array_plug[0]`` で要素を取得できるため、maya.cmds がシーケンスとして展開しようとして失敗する
     - ``str(plug)`` または ``plug.fullName()``。取得した要素・子も配列または複合なら文字列化する
   * - ``om2.MObject``
     - ``str()`` がオブジェクトの表現(``<OpenMaya.MObject ...>``)になる
     - ``hlib.node(mobject)`` の戻り値、または hlib のコマンド
   * - ``om2.MPlug``
     - ``str()`` が ``MPlug.name()`` で、短いノード名しか含まない。同じ短い名前のノードがあると曖昧になる
     - hlib の Plug(``Plug._resolve_input`` 相当の変換は hlib のコマンドと ``Plug.connectTo()`` が行う)

生の ``om2.MPlug`` は、削除操作をまたいで保持しないでください。hlib のコマンドと
ノードが必要な引数(``hlib.node``、``hlib.addConstraint`` の拘束元・拘束先など)は
``deleteAttr`` で削除されたアトリビュートの MPlug を ``ValueError`` にします(``Plug.connectTo()`` などのアトリビュートが必要な引数は ``RuntimeError``)が、Undo の対象から外れて削除されたノード(``flushUndo`` の後、Undo が無効な
状態での削除、``file(new=True)`` など)の MPlug は、``MPlug.node()`` の時点で Maya が
異常終了し、API では検出できません。保持する場合は hlib の Plug(ノードの削除を検出できる)を
使ってください。また MPlug はインスタンスの情報を持たないため、インスタンス化されたノードの
MPlug は最初のインスタンスとして扱います(Plug と文字列は名前が指すインスタンスを保持します)。

ワールド空間アトリビュート(``worldMatrix`` など)の ``ArrayPlug`` の ``str()`` (``g|c.worldMatrix``)は、
maya.cmds・``Plug._resolve_input()``・``hlib.node()`` では配列ではなく、名前が指すインスタンスの要素
(``worldMatrix[<インスタンス番号>]``)として解決されます。``cmds.getAttr(str(world), size=True)`` は
インスタンスの数によらず ``1`` を返し、``Plug._resolve_input(str(world))`` は要素の ``MatrixPlug`` です。
配列の要素を扱う場合は ``world.elements()``・``world[1]`` を使ってください。

.. code-block:: python

   network = hlib.createNode("network", name="valuesNode")
   values = network.addAttr("values", attributeType="double", multi=True)
   values[0].set(1.0)

   # cmds.getAttr(values, size=True)       # TypeError: ArrayPlug はそのまま渡せない
   print(cmds.getAttr(str(values), size=True))    # 1
   print(cmds.getAttr(values[0]))                 # 1.0（要素 Plug は渡せる）
   hlib.select(values)                            # hlib のコマンドは ArrayPlug も受け付ける

数値の受け渡し
------------------------------------------------------------

``maths`` の値は反復すると成分を返します。値を1つの引数として受け取らない
maya.cmds のフラグへ渡す場合は、次の点に注意してください。

- ``double3`` などの複合アトリビュートの ``cmds.setAttr`` は成分を ``*`` で展開します:
  ``cmds.setAttr(node.plug("t"), *Translate(1, 2, 3))``。
- ``EulerRotate`` の成分はラジアンです。度を受け取るフラグ(``cmds.xform(rotation=...)``、
  回転アトリビュートの ``cmds.setAttr``)には ``asDegrees()`` を渡します:
  ``cmds.xform(node, rotation=rotation.asDegrees())``。
- ``Matrix`` は行優先の16要素として展開できます:
  ``cmds.setAttr(plug, *matrix, type="matrix")``。

Plug の値は ``plug.get()``/``plug.set()`` でも扱えます。単位の扱いは :doc:`guide_plugs`、
数学型は :doc:`guide_maths` を参照してください。

hlib のコマンドが受け付ける入力
------------------------------------------------------------

``hlib.select``・``hlib.delete``・``hlib.duplicate``・``hlib.createGroup``・
``hlib.ls``・``hlib.bakeResults`` は、対象を次の規則で名前に
変換してから maya.cmds を呼びます(``parent`` などノードが必要な引数は後述。
``hlib.delete`` は Plug・MPlug を ``TypeError`` にします。「コマンドごとの注意」を参照)。

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - 入力
     - 変換後の名前
   * - ``str``
     - そのまま(Maya へ問い合わせない)
   * - ``Node``
     - ``fullName()`` (完全 DAG パス。DG ノードはノード名)
   * - ``Plug`` (``ArrayPlug`` を含む)
     - ``fullName()``。ArrayPlug は要素へ展開せず配列アトリビュートの名前になる
   * - ``Component`` (単体)
     - ``fullName()``
   * - ``Vertices`` などの複数形
     - 保持順で連続する番号を ``|cube|cubeShape.vtx[0:99]`` のような範囲指定にまとめる
       (``compactNames()``)。要素が多くても maya.cmds へ渡す名前が増えない
   * - ``Selection``、``Joints`` などのコレクション
     - 各要素の名前に展開する
   * - ``om2.MObject``
     - 依存ノードの完全 DAG パス、または DG ノード名。アトリビュートやコンポーネントの MObject は ``TypeError``
   * - ``om2.MDagPath``
     - ``fullPathName()`` (インスタンスのパスを保持)
   * - ``om2.MPlug``
     - ``Plug.fullName()`` と同じ形式
   * - list、tuple、set、ジェネレーター
     - 入れ子も含めて要素ごとに変換する

.. code-block:: python

   import maya.api.OpenMaya as om2
   from hlib.components import Vertices
   from hlib.common.selection import Selection

   hlib.select([dup1.plug("tx"), dup2.mnode(), Vertices(cube.shape(), [0, 1])])
   print(cmds.objExists(dup1.plug("tx").name()))   # True
   cmds.setKeyframe([dup1.plug("tx"), dup2.plug("ty")], time=1)
   hlib.select(Selection([dup1, vertex]))

対象としてノードが必要な引数(``hlib.node``、``hlib.addConstraint`` と
``Transform.addConstraint`` の拘束元・拘束先、``Node(...)``、
``hlib.createNode``/``hlib.createGroup`` の ``parent``、``Transform.setParent``、
``Node.parentOf`` など)は、Plug・MPlug・``"node.attribute"`` を所有ノード、
Component・Components・``"pCube1.vtx[0]"`` を所有シェイプとして扱います。
文字列も同じ規則で解決するため、maya.cmds のようにプラグ名・コンポーネント名が
拘束元として扱われない(または黙って無視される)ことはありません。
``parent`` にシェイプ(Component の所有シェイプを含む)を指定した場合の配置は
``maya.cmds.createNode`` と同じです。``hlib.addConstraint`` の ``target`` が Transform
(joint・IkHandle を含む)に解決されない場合は ``TypeError`` です。

``hlib.addConstraint``/``Transform.addConstraint`` の拘束元は、型によって扱いが異なります。

- parent・point・orient・scale・aim・poleVector は拘束元の transform の値を使うため、
  拘束元が Transform(joint・IkHandle を含む)に解決される必要があります。シェイプ
  (シェイプの Plug、Component・Components・``"pCube1.vtx[0]"`` の所有シェイプ)や DG ノードは
  ``TypeError`` です(maya.cmds はシェイプを拘束元にしてもターゲットの無い、追従しない
  拘束を黙って作るためです)。頂点の位置に拘束する場合は ``pointOnPoly`` などを使います。
- geometry・normal・tangent・pointOnPoly は、シェイプ・Component を拘束元にできます
  (所有シェイプ。Maya は拘束元をその親 Transform の名前で報告します)。
- 拘束元はノード単位です。Plug を渡すと Plug の所有ノード(Node が保持するインスタンスの
  パス)を使うため、``worldMatrix[1]`` のようなインスタンスごとの要素を渡しても要素番号の
  インスタンスにはなりません。特定のインスタンスは、そのパスの Node・文字列で指定して
  ください(MPlug はインスタンスの情報を持たないため、最初のインスタンスになります)。

アトリビュートが必要な引数(``Plug.connect``、``Plug.disconnect``、``Plug.connectedTo``、
``hlib.attr``、``hlib.plug``、``hlib.drivenKey``、``DrivenKey.find``)は、
Plug・MPlug とアトリビュート名の文字列を受け付けます。
文字列は ``str(plug)`` が返す形式(``grp1|dup.translateX``、``bs.weight[0]``、
エイリアス名の ``bs.smile``、``cubeShape.pnts[2].pntx`` など)も maya.cmds と同じ規則で解決します。
mesh の ``pnts[i]``、nurbsCurve・nurbsSurface・lattice の ``controlPoints[i]`` のように
コンポーネント名としても解釈される名前は、``cmds.connectAttr`` と同じくアトリビュートとして解決します
(``Selection`` は ``cmds.select`` と同じく頂点・CV として扱います。``hlib.node`` は
どちらの解釈でも所有シェイプを返します)。
``|box1.castsShadows`` のように transform の名前でシェイプのアトリビュートを指す場合も、
名前が指すインスタンスのシェイプ(``|box1|boxShape``)を所有ノードにします。
ただし transform の下にシェイプが複数ある場合(中間オブジェクトを除く)は、
``pCube1.pnts[3]`` や ``pCube1.castsShadows`` のようなシェイプのアトリビュート名を曖昧として
``RuntimeError`` にします。maya.cmds はこのような名前をすべてのシェイプのアトリビュートとして
展開します(``cmds.getAttr("pCube1.castsShadows")`` がシェイプごとの値のリストを返すなど)が、
Plug は1つのアトリビュートを表すためです。シェイプの名前で指定してください。

``hlib.attr(target)`` は ``hlib.plug(target)`` と同じ型付きPlug取得です。
既存Plugはそのまま返し、値は ``get()`` の内部単位(cm/rad/秒)または
``getu()`` のUI単位で読みます。照会フラグを一つでも指定した
``hlib.attr(target, **kwargs)`` は従来のMaya照会値・状態を返します。
``type=True`` 等の状態照会、``time``・``silent``・Falseの明示指定、
値のUI単位とMatrix・Vectorへの変換は維持します。
``maya.cmds.getAttr`` 自体の戻り値は変更していません。

.. code-block:: python

   print(hlib.node(dup1.plug("tx")))    # grp1|dup
   print(hlib.node(vertex))              # cubeShape（所有シェイプ）
   hlib.addConstraint(dup1.plug("tx"), dup2.mnode(), type="orient")  # 拘束元は dup1
   dup1.plug("sx").connectTo(dup2.plug("sx").mplug())

その他の規則です。

- 対象を名前へ変換する引数(上の表のコマンドの対象と、``hlib.createNode``/``hlib.createGroup``/
  ``BlendShape.addTarget`` などの ``parent``・ターゲットのようにノードの名前を渡す引数)の
  例外の種類は次のとおりです。

  - 対応しない型: ``TypeError``
  - 空文字列、空の om2 オブジェクト、削除済みの対象: ``ValueError``
  - 文字列を解決できない(存在しない、または ``"dup.tx"`` のように同じ短い名前のノードが
    あって複数の対象に一致する): ``RuntimeError``

  ``Node(...)``/``hlib.node`` は従来どおり、解決できない対象(空・削除済みを含む)を
  すべて ``RuntimeError`` にします(依存ノード以外を指す MObject は ``TypeError``)。
  ``hlib.addConstraint``/``Transform.addConstraint`` の拘束元・拘束先に削除済みの Node などを
  渡した場合も従来どおり ``RuntimeError`` です。
  ただし所有ノードは有効なまま ``deleteAttr`` でアトリビュートが削除された Plug・MPlug は、所有ノードへ
  解決せず、ノードが必要な引数(``Node(...)``/``hlib.node``、``hlib.addConstraint`` の拘束元・
  拘束先、``hlib.nodes.Node._resolve_input`` など)でも、名前へ変換する引数と同じく ``ValueError``
  です(``hlib.plugs.plug.DeletedAttributeError``。``RuntimeError`` の派生でもあるため、
  ``Node(...)`` の失敗を ``except RuntimeError`` で捕捉するコードもそのまま使えます)。
  ``Node.parentOf``/``childOf``/``ancestorOf`` の判定は、削除済みの対象
  (削除済みの Node、所有ノードが削除済みの Plug・Component、アトリビュートが削除済みの Plug・MPlug、
  削除済みのノードを指す om2 オブジェクト)には ``False`` を返します。
- 空の列は、``hlib.select([])`` が ``maya.cmds.select([])`` と同じく選択を解除し、
  ``hlib.ls([])`` と ``hlib.ls(None)`` は空の結果を返します(``cmds.listRelatives`` などが
  返す ``None`` をそのまま渡せます)。``hlib.delete([])`` と ``hlib.createGroup([])`` は
  ``ValueError`` (``group`` は ``empty=True`` を除く)です。いずれも maya.cmds のように現在の選択を対象にしないためです。
- ``Selection(...)`` も同じ型に加えて ``om2.MSelectionList`` を受け付けます。

コマンドごとの注意
------------------------------------------------------------

Plug・Component を受け付けるコマンドは一意な名前へ変換して maya.cmds を呼ぶため、
結果は maya.cmds の扱いに従います。

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - コマンド
     - Plug・Component を渡した場合
   * - ``hlib.delete``
     - Plug(``ArrayPlug`` を含む)・``om2.MPlug`` は ``TypeError`` です(列や ``Selection`` の
       要素に含まれる場合も、何も削除しません)。``maya.cmds.delete`` はアトリビュート名を渡しても
       エラーを表示するだけで何もしないためです。動的アトリビュートの削除は ``plug.delete()``、
       配列要素の削除は ``array_plug.removeElement(i)``、接続の解除は ``plug.disconnect()``、
       所有ノードの削除は ``hlib.delete(plug.node())`` を使います。Component は面の削除などに使えます。
   * - ``hlib.ls``
     - 結果はノードとしてラップするため、Plug は所有ノード、Component は所有シェイプに
       なります(``hlib.ls(plug)`` は ``[<所有ノード>]``。``cmds.ls`` はプラグ名を返します)。
   * - ``hlib.duplicate``
     - Plug は所有ノードを複製します(``cmds.duplicate`` と同じ)。Component の結果は
       ``cmds.duplicate`` に従い、Maya のバージョンとシーンの状態で変わります(Maya 2027 では
       オブジェクト全体を複製します。Maya 2022 では新しいシーンに立方体だけを作った状態などで
       ``RuntimeError`` (No object(s) to duplicate)になり、ほかのノードの作成後や頂点の選択中には
       オブジェクト全体を複製します)。オブジェクトを複製する場合はノードを渡してください。
   * - ``hlib.createGroup``
     - ``maya.cmds.group`` はアトリビュート・コンポーネントをグループ化しないため ``RuntimeError``
       (Not enough objects or values)になり、グループは作られません。``parent``/``p`` 引数の
       Plug は所有ノードを親にします。Component・シェイプは所有シェイプへ解決されますが、
       ``maya.cmds.group`` が Transform 以外の親を受け付けないため ``RuntimeError``
       (Transform node required for -parent flag)です。
   * - ``hlib.select``・``hlib.bakeResults``
     - maya.cmds と同じくアトリビュート・コンポーネントとして扱います(アトリビュートの選択・キー設定など)。

Node の生成
------------------------------------------------------------

``Node(value)`` と ``hlib.node(value)`` は、名前・MObject・MDagPath に加えて次を受け付け、
実際のノード型に対応するラッパー(``Joint``、``Mesh`` など)を返します。

- 既存の ``Node``: 同じノードとインスタンスを指す新しいラッパー。
- ``Plug``・``om2.MPlug``・``"node.attribute"`` 形式の名前: 所有ノード。
- ``Component``・``Components``・``"pCube1.vtx[0]"`` 形式の名前: 所有シェイプ。

インスタンス化されたノードの名前(``"|grpB|box1|boxShape.castsShadows"`` など)は、
名前が指すインスタンスのパスを保持します。ただし現在の選択(``Selection.capture()``)は
Maya がアトリビュートのインスタンスを保持しないため、インスタンスごとのアトリビュート(``worldMatrix[1]`` など)を
除いて最初のインスタンスになります(アトリビュートの値はどのインスタンスでも同じです)。

名前が存在しない・複数の対象に一致する場合、削除済みのラッパーや空・削除済みの
om2 オブジェクトを渡した場合は ``RuntimeError`` になります。アトリビュートだけが ``deleteAttr`` で
削除された Plug・MPlug は ``ValueError`` です(``RuntimeError`` としても捕捉できます)。

以前の hlib からの変更点
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

以前の ``Node(value)``/``hlib.node(value)`` は、複数のノードに一致する名前やパターン
(``"bulk*"`` など)を渡すと最初に一致したノードを黙って返していました。現在は
``RuntimeError`` です(一致が1つだけのパターンは、そのノードを返します)。
パターンに一致するノードを扱う場合は ``hlib.ls`` を使ってください。

.. code-block:: python

   # 以前: 最初の一致を返していた。現在は RuntimeError。
   # node = hlib.node("bulk*")
   nodes = hlib.ls("bulk*")       # 一致するすべてのノード
   first = nodes[0] if nodes else None
