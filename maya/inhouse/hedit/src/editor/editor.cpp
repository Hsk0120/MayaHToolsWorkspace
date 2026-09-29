/** @file editor.cpp
 * @brief editor.hの関数の実装。画面の本体はmain_window.cppにある。
 */
#include "editor/editor.h"
#include "editor/main_window.h"

namespace hedit {

QMainWindow* createEditor(QWidget* parent, const EditorServices& services) {
    return new MainWindow(parent, services);
}

void refreshEditorOutput(QMainWindow* editor) {
    // Mayaのreporterへの追記の途中で同期的に描画する。閉じたドックや終了処理中で
    // ネイティブウィンドウが無効な画面へ書くと、Qtのアクセシビリティ更新で落ちるため、表示中だけにする。
    // 非表示の間の出力はキューに残り、表示中の25msタイマーで反映される。
    if (!editor || !editor->isVisible()) {
        return;
    }
    // dynamic_castは、実際の型がMainWindowでなければnullptrを返す安全な変換。
    if (auto window = dynamic_cast<MainWindow*>(editor)) {
        window->refreshOutputNow();
    }
}

}  // namespace hedit
