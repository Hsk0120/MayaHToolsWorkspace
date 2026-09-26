/** @file spelling.cpp
 * @brief Windows同梱の英語辞書を1回のCOM呼出で照会し、語単位で結果をキャッシュする。
 */
#include "spelling.h"
#include <QHash>
#include <QSet>
#include <QRegularExpression>
#ifdef _WIN32
#define NOMINMAX
#include <windows.h>
#include <spellcheck.h>
#include <wrl/client.h>
#endif
namespace hedit {
/** @brief Qt側へWindowsヘッダーを公開しないための内部状態。 */
struct Spelling::Impl {
    bool attempted=false, ready=false, ownsCom=false;
    QHash<QString,bool> cache;
#ifdef _WIN32
    Microsoft::WRL::ComPtr<ISpellChecker> checker;
#endif
};
Spelling::Spelling() : impl(new Impl) {}
Spelling::~Spelling() {
#ifdef _WIN32
    impl->checker.Reset();
    if (impl->ownsCom) CoUninitialize();
#endif
}
bool Spelling::available() {
    if (impl->attempted) return impl->ready;
    impl->attempted=true;
#ifdef _WIN32
    HRESULT initialized=CoInitializeEx(nullptr,COINIT_APARTMENTTHREADED);
    impl->ownsCom=SUCCEEDED(initialized);
    if (FAILED(initialized) && initialized!=RPC_E_CHANGED_MODE) return false;
    Microsoft::WRL::ComPtr<ISpellCheckerFactory> factory;
    if (FAILED(CoCreateInstance(__uuidof(SpellCheckerFactory),nullptr,CLSCTX_INPROC_SERVER,IID_PPV_ARGS(&factory)))) return false;
    impl->ready=SUCCEEDED(factory->CreateSpellChecker(L"en-US",&impl->checker)) && impl->checker;
#endif
    return impl->ready;
}
QList<QPair<int,int>> Spelling::check(const QString& source) {
    QList<QPair<int,int>> result;
    if (!available()) return result;
    static const QStringList allowedWords=QString(
        "maya hlib hedit cmds pymel mel nurbs dag depsgraph attr attrs getattr setattr hasattr isinstance "
        "classmethod staticmethod dict kwargs args bool str repr init self none true false elif def import "
        "return yield lambda pass async await print super len range tuple list set type float enum viewport "
        "outliner keyframe quaternion blendshape skincluster multmatrix decompose uv fbx usd json utf api qt "
        "pyside shiboken plugin plugins callback callbacks stdout stderr sys pathlib os cspell").split(' ');
    static const QSet<QString> allowed(allowedWords.begin(),allowedWords.end());
    static const QRegularExpression words("[A-Z]?[a-z]+|[A-Z]+(?![a-z])");
    auto matches=words.globalMatch(source.left(8000));
    struct Word { QString value; int start; int length; };
    QList<Word> tokens, pending;
    QSet<QString> seen;
    QString query;
    while (matches.hasNext()) {
        auto match=matches.next(); auto value=match.captured().toLower();
        if (value.size()<4 || value.size()>40 || allowed.contains(value)) continue;
        tokens.append({value,int(match.capturedStart()),int(match.capturedLength())});
        if (!impl->cache.contains(value) && !seen.contains(value)) {
            pending.append({value,int(query.size()),int(value.size())}); query+=value+' '; seen.insert(value);
        }
    }
#ifdef _WIN32
    if (!query.isEmpty()) {
        Microsoft::WRL::ComPtr<IEnumSpellingError> errors;
        if (FAILED(impl->checker->Check(reinterpret_cast<LPCWSTR>(query.utf16()),&errors))) return result;
        // サイズ上限を設け、長時間の編集でもキャッシュが増え続けないようにする。
        if (impl->cache.size()>8192) impl->cache.clear();
        for (const auto& token: pending) impl->cache.insert(token.value,false);
        Microsoft::WRL::ComPtr<ISpellingError> error;
        while (errors->Next(&error)==S_OK && error) {
            ULONG start=0; CORRECTIVE_ACTION action=CORRECTIVE_ACTION_NONE;
            error->get_StartIndex(&start); error->get_CorrectiveAction(&action);
            if (action!=CORRECTIVE_ACTION_NONE) for (const auto& token: pending)
                if (int(start)>=token.start && int(start)<token.start+token.length) impl->cache[token.value]=true;
            error.Reset();
        }
    }
#endif
    for (const auto& token: tokens) if (impl->cache.value(token.value)) result.append({token.start,token.length});
    return result;
}
}
