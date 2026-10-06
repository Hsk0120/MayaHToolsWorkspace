Undo不要の値更新
================

対応する更新メソッドに ``fast=True`` を指定すると、OpenMayaで直接更新します。
省略時は従来のcmdsによるUndo対応処理です。シーン全体のUndo設定や既存履歴は変更しません。

.. code-block:: python

   import hlib

   node = hlib.getNode("pCube1")
   node.getPlug("translateX").set(10, fast=True)
   node.setTranslation((1, 2, 3), fast=True)

   shape = hlib.getNode("pCubeShape1")
   shape.getVertices().setPosition((0, 1, 0), fast=True)
   shape.getVertices().mirror(axis="x", fast=True)

   joints = hlib.ls(type="joint")
   joints.freezeRotation(fast=True)

対応範囲
--------

* Plugの ``set`` / ``reset`` とロック・keyable・channelBoxの設定。
  配列は要素Plugを取得して設定します。
* Transformの行列・translate・rotate・scale・shear・show・hide・形状ミラー。
* Joint / Jointsの ``freezeRotation`` と ``jointOrientToRotate``。
* NodeのOutliner色・override色・アトリビュート表示フラグ。
* 頂点・CVの単体／複数の座標設定とミラー、UVの単体／複数の座標設定。
* Shape / Transformの ``scaleGeometry``。履歴なしメッシュ・非周期カーブに対応。
* SkinClusterの ``setWeights`` / ``loadWeights`` / ``normalizeWeights`` /
  ``setMaxInfluences``。
* Locator、BlendColors、BlendWeighted、MultMatrix、DecomposeMatrix、
  DistanceBetween、Constraintの値設定メソッド。

対応メソッドから生成される複数形クラスの一括呼出しでも同じ引数を使用できます。
``AnimCurve.setInfinity`` の外挿設定も ``fast=True`` に対応します。
読み取りメソッドやプロパティ代入にはフラグはありません。
Mesh・NURBSカーブの座標取得は通常時もOpenMayaを使います。
単点取得では全点を読み出さず、複数点は保持順にまとめて取得します。
距離はcm、空間はws=True/Falseで指定し、履歴付き形状も読み取れます。
周期カーブもAPIのCV番号を使います。通常更新とcmdsへ渡す名前では末尾の重複CVを
対応する独立CVへ写します。fastの周期カーブ更新は未対応です。
ノード作成・削除・接続変更、アニメーションキー編集、ファイル・UI操作などには
このフラグを追加していません。個々のAPIリファレンスのシグネチャで確認してください。

動作と制限
----------

``fast=True`` の変更は、外側を ``undoChunk`` や ``undoTransaction`` で
囲んでも取り消せません。既存のUndo履歴が同じ値を操作すると、その値が上書きされる場合があります。
途中で例外が起きた場合も、完了済みの直接更新は自動では戻しません。

形状の直接編集は入力履歴のないメッシュ・非周期NURBSカーブに限定します。
スキニング等の入力履歴がある形状と周期カーブは ``NotImplementedError`` になります。
``scaleGeometry(fast=True)`` ではNURBSサーフェスも未対応です。
履歴付き形状の座標編集には通常モードを使用してください。
SkinClusterのウェイト更新は履歴付きメッシュでも使用できます。

Plugは数値・単位・enum・文字列・行列・対応するデータ配列を扱います。
未対応の型は ``NotImplementedError``、ロックや入力接続がある値はエラーになります。
型判定の結果は1回の更新内で再利用しますが、ロック・接続・値の範囲・UI単位は
更新するたびに確認します。削除されたアトリビュートの検証も省略しません。
fastの配列値設定では、MPlugの参照を取得して値を書き込む時に要素を実体化します。
型照会のための ``cmds.getAttr`` や、行列Plugの名前の再解決は挟みません。
doubleArray・Int32Array・stringArray・vectorArray・pointArrayの読取りもAPIを使い、
配列は常にlistです。空配列は[]、未初期化データはNone、点・ベクトルはtupleのlistです。
1要素でも外側のlistを省きません。
OpenMayaの直接設定はcmdsの全フラグを置き換えるものではありません。

重み付きCVのワールド座標はAPIのMPointのXYZ成分です。通常・fastの設定とも
CVのwを維持して逆変換し、取得値を同じ空間へ設定しても位置が変わらないようにします。

頂点・CV・UVではAPIの一括更新、ウェイトではMPlugの直接設定を使用します。
小さなアトリビュート更新まで常に高速になる保証はありません。
