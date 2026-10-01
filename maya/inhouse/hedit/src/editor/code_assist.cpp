/** @file code_assist.cpp
 * @brief CodeAssistの実装。
 */
#include "editor/code_assist.h"
#include "editor/code_editor.h"
#include "editor/editor_preferences.h"
#include "editor/problems_panel.h"
#include <QLabel>
#include <QTextBlock>
#include <QTextCursor>

namespace hedit {
namespace {

/// 補完・ホバーへ渡す本文の上限(文字数)。これを超える位置では問い合わせない。
constexpr int kDocumentLimit = 200000;

/// ステータスバーの補完の状態の、通常の文字。
constexpr const char* kReady = "Completion: ready (in Maya)";

/** @brief QTextCursorの選択文字列を、普通の改行の文字列にする。
 * @param text selectedText()の戻り値。行の区切りがU+2029(段落区切り)になっている。
 * @return 改行を``\n``にした文字列。
 */
QString normalizeSelectedText(QString text) {
    return text.replace(QChar(0x2029), '\n');
}

}  // namespace

CodeAssist::CodeAssist(const EditorServices& services, const EditorPreferences& preferences, ProblemsPanel* problems,
                       QLabel* completionStatus, Context context)
    : services_(services),
      preferences_(preferences),
      problems_(problems),
      completionStatus_(completionStatus),
      context_(std::move(context)) {
    // setSingleShot(true)のタイマーは、start()の後に1回だけtimeoutを出す。
    // 入力のたびにstart()し直すので、「最後の入力から○ms後」に1回だけ動く。
    completionTimer_.setSingleShot(true);
    completionTimer_.setInterval(250);
    connect(&completionTimer_, &QTimer::timeout, this, [this] { requestCompletion(false); });

    analysisTimer_.setSingleShot(true);
    analysisTimer_.setInterval(800);
    connect(&analysisTimer_, &QTimer::timeout, this, [this] { runAnalysis(); });

    spellingTimer_.setSingleShot(true);
    spellingTimer_.setInterval(450);
    connect(&spellingTimer_, &QTimer::timeout, this, [this] {
        CodeEditor* editor = context_.currentEditor();
        if (!preferences_.option(option::kSpellCheck) || !editor) {
            return;
        }
        editor->checkSpelling(spelling_);
        if (!spelling_.available()) {
            context_.showStatus("English spell-check dictionary is unavailable on this Windows installation", 5000);
        }
    });
}

void CodeAssist::attach(CodeEditor* editor) {
    editor->onCompletionRequested = [this] { requestCompletion(true); };
    // 接続先のeditorはタブと一緒に破棄されるが、関数はeditorが持つので、破棄後に呼ばれることはない。
    editor->onHoverRequested = [this, editor](int end) { return describe(editor, end); };
}

void CodeAssist::onTextChanged(CodeEditor* editor) {
    editor->clearSpelling();
    editor->hideCompletions();
    completionTimer_.stop();
    if (editor != context_.currentEditor()) {
        return;
    }
    // 候補の確定による変更では、次の自動補完を予約しない(Enterで確定した後、次のEnterで改行できる)。
    if (!editor->isInsertingCompletion()) {
        completionTimer_.start();
    }
    scheduleAnalysis();
    scheduleSpelling();
}

void CodeAssist::onCurrentChanged() {
    completionTimer_.stop();
    scheduleAnalysis();
    scheduleSpelling();
}

void CodeAssist::refreshCompletion() {
    if (services_.refreshCompletion) {
        services_.refreshCompletion();
    }
    hoverCache_ = HoverCache();
    completionStatus_->setText(kReady);
}

void CodeAssist::showCompletionError(const QString& error) {
    // Python側の失敗(hedit.bridgeの例外など)は、ここで初めて利用者に見える形にする。
    completionStatus_->setText("Completion: " + error);
    completionStatus_->setToolTip(error);
}

void CodeAssist::requestCompletion(bool force) {
    CodeEditor* editor = context_.currentEditor();
    if (!services_.complete || !editor || !editor->hasFocus() || editor->isMel()) {
        return;
    }
    QTextCursor cursor = editor->textCursor();
    // 直前の1文字がドットかを調べる(本文全体をコピーしない)。
    QTextCursor preceding = cursor;
    preceding.movePosition(QTextCursor::PreviousCharacter, QTextCursor::KeepAnchor);
    const bool afterDot = preceding.selectedText() == ".";
    if (!force) {
        // 自動補完は、設定でオンの場合だけ。名前の入力途中でもドットの直後でもなければ出さない。
        const bool enabled = afterDot ? preferences_.option(option::kCompleteDot)
                                      : preferences_.option(option::kCompleteLetters);
        if (!enabled) {
            return;
        }
        if (editor->completionPrefix().isEmpty() && !afterDot) {
            return;
        }
    }
    if (cursor.position() > kDocumentLimit) {
        completionStatus_->setText("Completion: document limit (200k)");
        return;
    }
    // 文書の先頭からカーソルまでを渡す。
    cursor.setPosition(0, QTextCursor::KeepAnchor);
    const CompletionResult result = services_.complete(normalizeSelectedText(cursor.selectedText()));
    if (!result.error.isEmpty()) {
        showCompletionError(result.error);
        return;
    }

    QList<CompletionItem> items;
    for (const CompletionItem& item : result.items) {
        if (item.kind == "keyword" && !preferences_.option(option::kIncludeKeywords)) {
            continue;
        }
        if (item.kind == "builtin" && !preferences_.option(option::kIncludeBuiltins)) {
            continue;
        }
        items.append(item);
    }
    completionStatus_->setText(kReady);
    completionStatus_->setToolTip(QString());
    editor->showCompletions(items);
    // import文の候補を別スレッドで集めている途中なら、少し後に問い合わせ直す(追加の入力は不要)。
    if (items.isEmpty() && result.pending) {
        completionTimer_.start(250);
    }
}

HoverInfo CodeAssist::describe(CodeEditor* editor, int end) {
    // 補完と同じ上限を超える大きな本文や、MELのタブでは説明を出さない。
    if (!services_.describe || editor->isMel() || editor->document()->characterCount() > kDocumentLimit) {
        return HoverInfo();
    }
    // 同じ名前の上でマウスが止まるたびにQtはQEvent::ToolTipを送る。本文が変わっていなければ前回の結果を使い、
    // 本文全体の複製とPythonへの問い合わせを省く。
    const int revision = editor->document()->revision();
    if (hoverCache_.editor == editor && hoverCache_.revision == revision && hoverCache_.end == end) {
        return hoverCache_.info;
    }
    const HoverInfo info = services_.describe(editor->toPlainText(), end);
    hoverCache_.editor = editor;
    hoverCache_.revision = revision;
    hoverCache_.end = end;
    hoverCache_.info = info;
    return info;
}

void CodeAssist::scheduleAnalysis() {
    analysisTimer_.stop();
    problems_->clear();
    CodeEditor* editor = context_.currentEditor();
    const bool enabled = preferences_.option(option::kStaticAnalysis) && editor && !editor->isMel();
    problems_->setVisible(enabled);
    if (enabled) {
        problems_->showWaiting();
        analysisTimer_.start();
    }
}

void CodeAssist::runAnalysis() {
    CodeEditor* editor = context_.currentEditor();
    if (!preferences_.option(option::kStaticAnalysis) || !services_.analyze || !editor || editor->isMel()) {
        return;
    }
    problems_->showResult(services_.analyze(editor->toPlainText()));
}

void CodeAssist::scheduleSpelling() {
    spellingTimer_.stop();
    if (!preferences_.option(option::kSpellCheck)) {
        for (CodeEditor* editor : context_.editors()) {
            editor->clearSpelling();
        }
        return;
    }
    if (context_.currentEditor()) {
        spellingTimer_.start();
    }
}

}  // namespace hedit
