設定の作用範囲と保存先
============================

hlibでは操作する概念ごとにクラスを選び、保存ファイル名ごとのクラスには分割しません。
``Preferences`` は値を保持するデータクラスではなく、現在のMaya設定の操作窓口です。
getメソッドは呼ぶたびにMayaへ問い合わせ、setメソッドはMayaへ変更を反映します。
UIで変更した値を取得するためにインスタンスを作り直す必要はありません。

設定を変えることと、次回利用のためファイルへ保存することは別の操作です。

保存先の一覧
----------------------------

.. list-table::
   :header-rows: 1
   :widths: 20 25 30 25

   * - 対象
     - 作用範囲
     - 保存先
     - 保存・復元
   * - 距離・角度・時間単位
     - 現在のシーン
     - シーンファイル (.ma / .mb)
     - シーン保存・読み込み。新規シーンの既定値とは別
   * - 上方向・Undo設定・選択順・自動保存設定
     - 現在のMaya
     - ユーザー設定 (主にuserPrefs.mel)
     - Maya標準の設定保存・起動時の復元。下記の同期の注意点を参照
   * - シェルフとボタン
     - MayaのシェルフUI
     - prefs/shelves配下のMELファイル
     - Mayaのシェルフ保存機能・起動時のロード
   * - ウィンドウの位置・サイズ
     - MayaのUI
     - windowPrefs.melなど
     - MayaのUI設定保存・復元。ドッキング配置とは保存機構が異なる
   * - プロジェクトのファイルルール
     - 現在のプロジェクト
     - プロジェクト直下のworkspace.mel
     - Mayaのプロジェクト設定保存・プロジェクト切り替え時の読み込み

``Scene`` はシーン、``Workspace`` はプロジェクト、``Preferences`` は設定操作を担当します。
シェルフとボタンは ``Shelf`` / ``ShelfButton`` で操作できます。:doc:`shelves` を参照してください。
自動保存の「設定」はユーザー設定ですが、保存されるシーン本体は自動保存先のファイルです。
Undoの有効状態や上限設定と、操作履歴そのものも別です。Undo履歴は再起動で復元されません。

Preferencesの各メソッド
----------------------------

.. list-table:: メソッド名のget / set接頭辞に続く名前
   :header-rows: 1

   * - 名前
     - 対象・保存区分
   * - linear_unit / angle_unit / time_unit
     - 現在のシーンの単位。シーン保存時に保持
   * - up_axis
     - Mayaの上方向。ユーザー設定
   * - undo_enabled / undo_infinite / undo_limit
     - MayaのUndo設定。ユーザー設定
   * - track_selection_order
     - Mayaの選択順記録設定。ユーザー設定
   * - autosave_enabled / autosave_interval / autosave_directory
     - Mayaの自動保存設定。ユーザー設定

単位以外のsetメソッドの既定は ``save=False`` です。現在値だけ変更し、設定ファイルは保存しません。
``save=True`` または ``Preferences.save()`` で、上方向・Undo・選択順・自動保存の
現在値を保存用optionVarへ同期し、Maya標準のMELコマンド ``savePrefs -general`` を実行します。
保存はMaya GUI専用です。batch / standaloneのsave=Trueは現在値を変更する前にRuntimeErrorになります。
一般optionVar全体が書き出されるため、他の一般設定も保存対象になります。
シーン・シェルフ・UI配置の保存は行いません。ディスクへの保存はUndoで戻りません。
保存失敗は例外として通知し、既に変更した現在値は巻き戻しません。

.. code-block:: python

   from hlib.common import Preferences

   prefs = Preferences()
   prefs.setTrackSelectionOrder(True, save=True)
   prefs.setUndoLimit(100)
   prefs.setAutosaveInterval(600)
   prefs.save()  # 対応するユーザー設定をまとめて同期・保存

単位はシーン側の設定です。``setLinearUnit`` / ``setAngleUnit`` / ``setTimeUnit``
にsaveフラグはありません。単位を保持するにはScene.save()でシーンを保存してください。
新規シーンの既定値には転記しません。

ウィンドウの配置操作は :doc:`window_layouts` を参照してください。

保存先を確認する
----------------------------

Windowsの標準位置は ``Documents/maya/<version>/prefs`` ですが、環境変数
``MAYA_APP_DIR`` 等により変わるため固定パスを組み立てずMayaへ問い合わせます。

.. code-block:: python

   import maya.cmds as cmds
   from hlib.common import Preferences

   prefs = Preferences()
   print(prefs.getLinearUnit())  # 現在値の照会のみ
   print(cmds.internalVar(userPrefDir=True))
   print(cmds.internalVar(userShelfDir=True))

退避用データとの違い
----------------------------

設定の比較・復元・JSON出力が必要になった場合に、取得時点の値を保持する
スナップショット用データを別途設計します。現在のPreferencesはスナップショットを
保持せず、capture/applyメソッドも実装していません。

操作例は :doc:`guide_environment`、シーン保存は :doc:`guide_files` を参照してください。

参考
----------------------------

* `Mayaの設定ファイルの種類 <https://help.autodesk.com/cloudhelp/2026/ENU/Maya-Customizing/files/GUID-280FE025-66DF-4DF8-AD44-417DC202A889.htm>`_
* `savePrefsの保存対象 <https://help.autodesk.com/cloudhelp/2026/ENU/Maya-Tech-Docs/CommandsPython/savePrefs.html>`_
