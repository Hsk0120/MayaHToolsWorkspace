/** @file spelling.cpp
 * @brief Windows同梱の英語辞書を1回のCOM呼出しで照会し、単語ごとに結果をキャッシュする。
 */
#include "editor/spelling.h"
#include <QHash>
#include <QRegularExpression>
#include <QSet>
#include <QStringList>
#ifdef _WIN32
#define NOMINMAX
#include <windows.h>
#include <spellcheck.h>
#include <wrl/client.h>
#endif

namespace hedit {
namespace {

/// キャッシュの件数の上限。超えたら空にする(長時間の編集で増え続けないように)。
constexpr int kMaximumCachedWords = 8192;

/** @brief スペルミスとして扱わない、Maya・Pythonでよく使う語。
 * @return 小文字の語の集合。
 */
const QSet<QString>& allowedWords() {
    static const QStringList words = QString(
        "maya hlib hedit cmds pymel mel nurbs dag depsgraph attr attrs getattr setattr hasattr isinstance "
        "classmethod staticmethod dict kwargs args bool str repr init self none true false elif def import "
        "return yield lambda pass async await print super len range tuple list set type float enum viewport "
        "outliner keyframe quaternion blendshape skincluster multmatrix decompose uv fbx usd json utf api qt "
        "pyside shiboken plugin plugins callback callbacks stdout stderr sys pathlib os cspell").split(' ');
    static const QSet<QString> allowed(words.begin(), words.end());
    return allowed;
}

}  // namespace

/** @brief Windows固有の状態。ヘッダーにWindowsの型を出さないため、ここで定義する。 */
struct Spelling::Impl {
    bool attempted = false;       ///< 初期化を試したか。
    bool ready = false;           ///< 辞書が使えるか。
    bool ownsCom = false;         ///< COMをこのクラスが初期化したか(したなら破棄時に解放する)。
    QHash<QString, bool> cache;   ///< 単語 → スペルミスならtrue。
#ifdef _WIN32
    Microsoft::WRL::ComPtr<ISpellChecker> checker;  ///< ComPtrは参照カウントを自動で管理するポインター。
#endif
};

Spelling::Spelling() : impl_(new Impl) {}

Spelling::~Spelling() {
#ifdef _WIN32
    impl_->checker.Reset();
    if (impl_->ownsCom) {
        CoUninitialize();
    }
#endif
}

bool Spelling::available() {
    if (impl_->attempted) {
        return impl_->ready;
    }
    impl_->attempted = true;
#ifdef _WIN32
    // Mayaが既に別の方式でCOMを初期化していればRPC_E_CHANGED_MODEになる。その場合もそのまま使える。
    const HRESULT initialized = CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
    impl_->ownsCom = SUCCEEDED(initialized);
    if (FAILED(initialized) && initialized != RPC_E_CHANGED_MODE) {
        return false;
    }
    Microsoft::WRL::ComPtr<ISpellCheckerFactory> factory;
    if (FAILED(CoCreateInstance(__uuidof(SpellCheckerFactory), nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&factory)))) {
        return false;
    }
    impl_->ready = SUCCEEDED(factory->CreateSpellChecker(L"en-US", &impl_->checker)) && impl_->checker;
#endif
    return impl_->ready;
}

QList<QPair<int, int>> Spelling::check(const QString& source) {
    QList<QPair<int, int>> result;
    if (!available()) {
        return result;
    }
    // 大文字で始まる語・小文字の語・大文字だけの語に分ける(camelCaseやsnake_caseも分かれる)。
    static const QRegularExpression wordPattern("[A-Z]?[a-z]+|[A-Z]+(?![a-z])");

    /** 1つの単語と、その位置。 */
    struct Word {
        QString value;
        int start;
        int length;
    };
    QList<Word> words;          // 表示範囲の全ての単語(結果を返すため)。
    QList<Word> uncachedWords;  // 辞書へ問い合わせる単語。startとlengthはquery内の位置。
    QSet<QString> queued;
    QString query;              // 問い合わせる単語を空白でつないだ文字列(1回のCOM呼出しにまとめる)。

    auto matches = wordPattern.globalMatch(source.left(8000));
    while (matches.hasNext()) {
        const auto match = matches.next();
        const QString value = match.captured().toLower();
        if (value.size() < 4 || value.size() > 40 || allowedWords().contains(value)) {
            continue;
        }
        words.append({value, int(match.capturedStart()), int(match.capturedLength())});
        if (!impl_->cache.contains(value) && !queued.contains(value)) {
            uncachedWords.append({value, int(query.size()), int(value.size())});
            query += value + ' ';
            queued.insert(value);
        }
    }
#ifdef _WIN32
    if (!query.isEmpty()) {
        Microsoft::WRL::ComPtr<IEnumSpellingError> errors;
        if (FAILED(impl_->checker->Check(reinterpret_cast<LPCWSTR>(query.utf16()), &errors))) {
            return result;
        }
        if (impl_->cache.size() > kMaximumCachedWords) {
            impl_->cache.clear();
        }
        // いったん全て「正しい」として登録し、辞書が指摘した単語だけtrueにする。
        for (const Word& word : uncachedWords) {
            impl_->cache.insert(word.value, false);
        }
        Microsoft::WRL::ComPtr<ISpellingError> error;
        while (errors->Next(&error) == S_OK && error) {
            ULONG start = 0;
            CORRECTIVE_ACTION action = CORRECTIVE_ACTION_NONE;
            error->get_StartIndex(&start);
            error->get_CorrectiveAction(&action);
            if (action != CORRECTIVE_ACTION_NONE) {
                for (const Word& word : uncachedWords) {
                    if (int(start) >= word.start && int(start) < word.start + word.length) {
                        impl_->cache[word.value] = true;
                    }
                }
            }
            error.Reset();
        }
    }
#endif
    for (const Word& word : words) {
        if (impl_->cache.value(word.value)) {
            result.append({word.start, word.length});
        }
    }
    return result;
}

}  // namespace hedit
