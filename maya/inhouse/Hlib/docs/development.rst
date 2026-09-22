構成とドキュメント更新
======================

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
   * - ``scene``
     - Scene と Namespace によるシーン・名前空間操作
   * - ``maths``
     - Vector、Matrix、Quaternion などの数学型（Matrix 以外は frozen dataclass）
   * - ``cmds``
     - ``maya.cmds`` 相当の手続き的 API（create_node、ls、constraint）
   * - ``decorators``
     - Undo チャンク、選択状態の保存・復元、Undo チャンク化デコレータ
   * - ``utils``
     - ログと進捗表示
   * - ``core``
     - 型登録、ラッパー検出、初期化、再読み込みの内部基盤

API の生成方針
--------------

Sphinx AutoAPI が Python ソースと docstring を静的解析します。
ビルド時に Hlib・Maya を import せず、テストスクリプトも実行しません。
``__tests__`` は生成対象から除外しています。

Hlib は実行時にラッパーを発見して公開 API を構成するため、
動的に追加される別名は静的解析では列挙されません。
各クラスの詳細は、定義元のモジュール（例: ``Hlib.nodes.joint``）を参照してください。
継承したメソッドは基底クラスのページを参照します。
非公開メソッドと特殊メソッドも掲載し、初期化の引数は ``__init__`` の詳細に記載します。

クラスごとに独立したページを生成し、cymel の API リファレンスに合わせて
``Methods:`` にメソッド名・シグネチャ・概要の一覧、``Methods Details:`` に
各メソッドの詳細をアルファベット順で掲載します。
一覧では省略可能な引数を角括弧で、詳細では既定値付きで表示します。
属性は ``Attributes:`` に掲載します。
引数・戻り値・戻り値の型は docstring から生成し、API 名は実装に従います。
表記用テンプレートは ``_templates/autoapi/python/class.rst`` で管理し、
配色やナビゲーションは PyData テーマを使用します。

更新方法
--------

関数・クラスの説明は実装の docstring を更新します。
既存コードに合わせて Google 形式の ``Args:``、``Returns:``、``Raises:`` を
使用すると、Napoleon 拡張が整形します。
引数は ``self`` / ``cls`` を除いて記載し、既定値・単位・省略時の動作を説明します。
値を返さない処理は ``Returns:`` に ``None``、ジェネレータは ``Yields:``、
必ず例外を送出する処理は ``NoReturn`` として記載します。
新しいモジュールは Hlib 配下に追加すると次回ビルドで検出されます。
利用手順はこのディレクトリの ``.rst`` に記述します。

ビルド環境の作成とコマンドは ``maya/inhouse/Hlib/docs/README.md`` を参照してください。
生成 HTML は ``maya/inhouse/Hlib/docs/_build/html`` に出力し、Git には含めません。

参考: `Sphinx AutoAPI の公式ドキュメント <https://sphinx-autoapi.readthedocs.io/en/latest/>`_


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
基底クラスは ``Hlib.components`` から import できます。
