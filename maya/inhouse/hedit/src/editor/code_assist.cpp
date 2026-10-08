/** @file code_assist.cpp
 * @brief CodeAssistの実装。
 */
#include "editor/code_assist.h"
#include "core/signature_help.h"
#include "editor/code_editor.h"
#include "editor/editor_preferences.h"
#include "editor/hover_popup.h"
#include "editor/problems_panel.h"
#include <QLabel>
#include <QTextBlock>
#include <QTextCursor>

namespace hedit {
namespace {

/// 補完・ホバーへ渡す本文の上限(文字数)。これを超える位置では問い合わせない。
constexpr int kDocumentLimit = 200000;

/// 引数のヒントで、カーソルより前を読む文字数の目安(呼出しの括弧はこの中にあるとみなす)。
constexpr int kSignatureContext = 4000;

/// この数より少ない候補なら、名前を後ろへ伸ばしたときに一覧の絞り込みだけで足りる
/// (補完の候補は最大250件。上限に近いと、伸ばした名前の候補が前回の一覧に入っていないことがある)。
/// 上限に近かった場合は、一覧を開いたまま、その場で候補を求め直して入れ替える。
constexpr int kRefilterLimit = 200;

/// ステータスバーの補完の状態の、通常の文字。
constexpr const char* kReady = "Completion: ready (in Maya)";

/** @brief QTextCursorの選択文字列を、普通の改行の文字列にする。
 * @param text selectedText()の戻り値。行の区切りがU+2029(段落区切り)になっている。
 *        Shift+Enterや以前の貼り付けで入ったU+2028(行区切り)も含みうる。
 * @return 改行を``\n``にした文字列。
 */
QString normalizeSelectedText(QString text) {
    return text.replace(QChar(0x2029), '\n').replace(QChar(0x2028), '\n');
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

    signatureTimer_.setSingleShot(true);
    signatureTimer_.setInterval(60);
    connect(&signatureTimer_, &QTimer::timeout, this, [this] {
        if (signatureEditor_) {
            updateSignatureHelp(signatureEditor_);
        }
    });
    detailTimer_.setSingleShot(true);
    detailTimer_.setInterval(120);
    connect(&detailTimer_, &QTimer::timeout, this, [this] {
        if (detailEditor_) {
            updateCompletionDetail(detailEditor_);
        }
    });

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
    editor->onSignatureHelpRequested = [this, editor](bool explicitRequest) {
        signatureEditor_ = editor;
        if (explicitRequest) {
            updateSignatureHelp(editor);
        } else {
            signatureTimer_.start();
        }
    };
    editor->onCompletionSelectionChanged = [this, editor] {
        detailEditor_ = editor;
        detailTimer_.start();
    };
}

void CodeAssist::updateSignatureHelp(CodeEditor* editor) {
    if (!services_.describe || editor != context_.currentEditor() || editor->isMel() || !editor->hasFocus()) {
        editor->hideSignatureHelp();
        return;
    }
    QTextCursor cursor = editor->textCursor();
    if (cursor.hasSelection() || cursor.position() > kDocumentLimit) {
        editor->hideSignatureHelp();
        return;
    }
    int base = 0;
    const QString searchText = callSearchText(editor, &base);
    CallContext call = findCallContext(searchText);
    if (call.nameEnd < 0) {
        signatureCache_ = SignatureCache();  // 呼出しの外へ出たら、次の呼出しでは説明を求め直す。
        editor->hideSignatureHelp();
        return;
    }
    // 同じ呼出しの引数を入力している間(名前の位置と、その行の名前までが同じ)は、前回の説明を使う。
    const int lineStart = searchText.lastIndexOf('\n', call.nameEnd - 1) + 1;
    const QString callee = searchText.mid(lineStart, call.nameEnd - lineStart);
    call.nameEnd += base;  // 取り出した本文の中の位置 → 文書の中の位置。
    call.openParen += call.openParen >= 0 ? base : 0;
    const bool cached = signatureCache_.editor == editor && signatureCache_.nameEnd == call.nameEnd
                        && signatureCache_.callee == callee;
    if (!cached) {
        signatureCache_.editor = editor;
        signatureCache_.nameEnd = call.nameEnd;
        signatureCache_.callee = callee;
        signatureCache_.info = describe(editor, call.nameEnd);
        signatureCache_.init = HoverInfo();
        if (signatureCache_.info.signature.startsWith("class ")) {
            const QString text = normalizeSelectedText(editor->toPlainText()).left(call.nameEnd) + ".__init__";
            signatureCache_.init = services_.describe(text, text.size());
        }
    }
    HoverInfo info = signatureCache_.info;
    SignatureParts parts = splitSignature(info.signature);
    if (info.signature.startsWith("class ")) {
        // クラスの呼出しは __init__ の引数を出す(self を除く)。
        const HoverInfo& init = signatureCache_.init;
        parts = splitSignature(init.signature);
        dropBoundParameter(&parts);
        if (info.doc.isEmpty()) {
            info.doc = init.doc;
        }
    } else if (call.attribute) {
        dropBoundParameter(&parts);  // obj.method( では self を渡さない。
    }
    const QString family = editor->font().family();
    if (parts.valid) {
        const int active = activeParameterIndex(parts.parameters, call.argumentIndex, call.keyword);
        editor->showSignatureHelp(HoverPopup::signatureHelpHtml(parts, active, info.doc, family));
    } else if (!info.isEmpty()) {
        editor->showSignatureHelp(HoverPopup::toHtml(info, family));
    } else {
        editor->hideSignatureHelp();
    }
}

void CodeAssist::updateCompletionDetail(CodeEditor* editor) {
    const QString name = editor->currentCompletion();
    if (!services_.describe || name.isEmpty() || editor->isMel()) {
        editor->hideCompletionDetail();
        return;
    }
    QTextCursor cursor = editor->textCursor();
    if (cursor.position() > kDocumentLimit) {
        return;
    }
    // 同じ本文で同じ候補を選び直したときは、前回の説明を使う(候補を上下に動かすたびに問い合わせ直さない)。
    const int revision = editor->document()->revision();
    if (detailCache_.editor != editor || detailCache_.revision != revision) {
        detailCache_.editor = editor;
        detailCache_.revision = revision;
        detailCache_.infos.clear();
    }
    const QString prefix = editor->completionPrefix();
    const QString key = prefix + '|' + name;
    const auto found = detailCache_.infos.constFind(key);
    if (found != detailCache_.infos.constEnd()) {
        editor->showCompletionDetail(*found);
        return;
    }
    // 入力途中の名前を、選んでいる候補に置き換えた本文で説明を求める(本文は変更しない)。
    cursor.setPosition(0, QTextCursor::KeepAnchor);
    QString before = normalizeSelectedText(cursor.selectedText());
    before.chop(prefix.size());
    const QString text = before + name;
    const HoverInfo info = services_.describe(text, text.size());
    detailCache_.infos.insert(key, info);
    editor->showCompletionDetail(info);
}

QString CodeAssist::callSearchText(CodeEditor* editor, int* base) {
    const QTextCursor cursor = editor->textCursor();
    const int position = cursor.position();
    // 目安の文字数だけ前の行から始める。ただし前の行の終わりが行をまたぐ文字列・コメントの途中なら
    // (構文強調が行ごとに残す状態が通常でなければ)、通常の状態から始まる行までさかのぼる。
    QTextBlock block = cursor.block();
    while (block.previous().isValid()
           && (position - block.position() < kSignatureContext || block.previous().userState() > 0)
           && position - block.position() < kDocumentLimit) {
        block = block.previous();
    }
    QTextCursor range(editor->document());
    range.setPosition(block.position());
    range.setPosition(position, QTextCursor::KeepAnchor);
    *base = block.position();
    return normalizeSelectedText(range.selectedText());
}

void CodeAssist::onTextChanged(CodeEditor* editor) {
    completionTimer_.stop();
    // 補完の一覧を開いていれば、閉じずに入力した名前で絞り込む(入力のたびに閉じて開き直さない)。
    // スペルの波線は、コード欄が編集した単語の分だけ消す(全体を消すと入力のたびにちらつく)。
    const bool truncated = completionEditor_ == editor && completionCount_ >= kRefilterLimit;
    const bool kept = editor->refilterCompletions(truncated && !editor->isInsertingCompletion());
    if (editor != context_.currentEditor()) {
        editor->hideCompletions();
        return;
    }
    // 候補の確定による変更では、次の自動補完を予約しない(Enterで確定した後、次のEnterで改行できる)。
    if (!editor->isInsertingCompletion()) {
        const bool extended = kept && completionEditor_ == editor
                              && editor->completionPrefix().startsWith(completionPrefix_);
        if (kept && truncated) {
            // 前回の候補は上限で切れていた: 一覧を開いたまま、すぐ求め直して入れ替える(一度閉じると、ちらつく)。
            requestCompletion(false);
        } else if (!extended) {
            completionTimer_.start();  // 名前を短くした・別の名前になった: 入力が止まってから求め直す。
        }
        // 名前を後ろへ伸ばしただけで、前回の候補が上限に達していなければ、絞り込んだ一覧のままでよい。
    }
    scheduleAnalysis(true);
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
    completionEditor_ = editor;
    completionPrefix_ = editor->completionPrefix();
    completionCount_ = result.items.size();

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

void CodeAssist::scheduleAnalysis(bool keepResults) {
    analysisTimer_.stop();
    CodeEditor* editor = context_.currentEditor();
    const bool enabled = preferences_.option(option::kStaticAnalysis) && editor && !editor->isMel();
    problems_->setVisible(enabled);
    if (!preferences_.option(option::kStaticAnalysis)) {
        // 構文チェックをオフにしたら波線も消す(既に空のタブでは何もしない)。
        for (CodeEditor* each : context_.editors()) {
            each->setDiagnostics({});
        }
    } else if (editor && editor->isMel()) {
        editor->setDiagnostics({});
    }
    if (!enabled) {
        problems_->clear();
        return;
    }
    // 入力中は前回の結果を残したまま待ち、結果が出たら置き換える(入力のたびに一覧を「確認中」へ戻さない)。
    if (!keepResults || problems_->count() == 0) {
        problems_->showWaiting();
    }
    analysisTimer_.start();
}

void CodeAssist::runAnalysis() {
    CodeEditor* editor = context_.currentEditor();
    if (!preferences_.option(option::kStaticAnalysis) || !services_.analyze || !editor || editor->isMel()) {
        return;
    }
    const AnalysisResult result = services_.analyze(editor->toPlainText());
    problems_->showResult(result);
    editor->setDiagnostics(result.diagnostics);  // 本文にも波線を引く(説明はホバーとF8)。
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
