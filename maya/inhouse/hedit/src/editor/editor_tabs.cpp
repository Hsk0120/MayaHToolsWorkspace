/** @file editor_tabs.cpp
 * @brief ScrollTabBarとEditorTabsの実装。
 */
#include "editor/editor_tabs.h"
#include "editor/code_editor.h"
#include <QFileInfo>
#include <QWheelEvent>

namespace hedit {

ScrollTabBar::ScrollTabBar(QWidget* parent) : QTabBar(parent) {
    setUsesScrollButtons(true);
    setExpanding(false);
    setElideMode(Qt::ElideNone);
}

void ScrollTabBar::wheelEvent(QWheelEvent* event) {
    // 縦のホイールを優先し、無ければ横(タッチパッドの横スクロール)を使う。
    int delta = event->angleDelta().y();
    if (delta == 0) {
        delta = event->angleDelta().x();
    }
    if (delta != 0 && count() > 0) {
        const int step = delta < 0 ? 1 : -1;
        setCurrentIndex(qBound(0, currentIndex() + step, count() - 1));
    }
    event->accept();
}

EditorTabs::EditorTabs(QWidget* parent) : QTabWidget(parent) {
    // setTabBarで渡したタブバーは、このタブ欄が所有する。
    setTabBar(new ScrollTabBar(this));
    setTabsClosable(true);
    setMovable(true);
}

CodeEditor* EditorTabs::currentEditor() const {
    // タブにはCodeEditorしか入れないので、static_castで型を戻してよい。
    return static_cast<CodeEditor*>(currentWidget());
}

CodeEditor* EditorTabs::editorAt(int index) const {
    return static_cast<CodeEditor*>(widget(index));
}

QList<CodeEditor*> EditorTabs::editors() const {
    QList<CodeEditor*> result;
    for (int i = 0; i < count(); ++i) {
        result.append(editorAt(i));
    }
    return result;
}

QStringList EditorTabs::filePaths() const {
    QStringList paths;
    for (CodeEditor* editor : editors()) {
        if (!editor->filePath().isEmpty()) {
            paths.append(editor->filePath());
        }
    }
    return paths;
}

int EditorTabs::indexOfFile(const QString& absolutePath) const {
    for (int i = 0; i < count(); ++i) {
        if (QFileInfo(editorAt(i)->filePath()).absoluteFilePath() == absolutePath) {
            return i;
        }
    }
    return -1;
}

void EditorTabs::updateTitle(CodeEditor* editor) {
    const QString marker = editor->document()->isModified() ? " ●" : "";
    setTabText(indexOf(editor), editor->displayName() + marker);
}

void EditorTabs::switchTab(int direction) {
    setCurrentIndex((currentIndex() + direction + count()) % count());
}

}  // namespace hedit
