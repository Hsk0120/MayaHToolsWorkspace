/** @file shell_recycle.cpp @brief COM STAは呼出ワーカー内だけで初期化する。 */
#include "shell_recycle.h"
#include <QDir>
#include <QFileInfo>
#include <QFile>
#include <stdexcept>
#define NOMINMAX
#include <windows.h>
#include <shobjidl.h>
#include <shlguid.h>
#include <wrl/client.h>
using Microsoft::WRL::ComPtr;
namespace qpe {
namespace {
/** @brief HRESULTを例外に変換する。 @param hr 結果。 */
void checked(HRESULT hr) { if (FAILED(hr)) throw std::runtime_error(QString("Windows Shell error 0x%1").arg(quint32(hr), 8, 16, QChar('0')).toStdString()); }
/** @brief COM解放を例外時も対にする。 */
struct Apartment {
    /** @brief 呼出スレッドをSTAにする。 */
    Apartment() { checked(CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED)); }
    /** @brief 自分の初期化だけを解放する。 */
    ~Apartment() { CoUninitialize(); }
};
/** @brief Shell項目を得る。 @param path 解析名。 @return 所有参照。 */
ComPtr<IShellItem> item(const QString& path) {
    ComPtr<IShellItem> result;
    // Qtの内部表記「/」をShellのファイルシステム解析名「\」に変換する。
    // shell:RecycleBinFolderなどの仮想解析名は変更しない。
    const auto parsing = QFileInfo(path).isAbsolute() ? QDir::toNativeSeparators(path) : path;
    const auto status = SHCreateItemFromParsingName(reinterpret_cast<LPCWSTR>(parsing.utf16()), nullptr, IID_PPV_ARGS(&result));
    if (FAILED(status)) throw std::runtime_error(QString("Cannot resolve Shell item (0x%1): %2").arg(quint32(status), 8, 16, QChar('0')).arg(parsing).toStdString());
    return result;
}
/** @brief Shell名をコピーしてallocatorを解放する。 @param value 項目。 @param kind 名前種別。 @return 名前。 */
QString name(IShellItem* value, SIGDN kind) {
    PWSTR buffer = nullptr; checked(value->GetDisplayName(kind, &buffer));
    const auto result = QString::fromWCharArray(buffer); CoTaskMemFree(buffer); return result;
}
/** @brief 内容を読まずIDを得る。 @param path 物理パス。 @return volume/file ID。 */
QString identity(const QString& path) {
    const HANDLE handle = CreateFileW(reinterpret_cast<LPCWSTR>(path.utf16()), 0,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, nullptr, OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS, nullptr);
    if (handle == INVALID_HANDLE_VALUE) throw std::runtime_error(QString("Cannot inspect Shell item (%1): %2").arg(GetLastError()).arg(path).toStdString());
    BY_HANDLE_FILE_INFORMATION info{};
    const BOOL ok = GetFileInformationByHandle(handle, &info); const DWORD error = GetLastError(); CloseHandle(handle);
    if (!ok) checked(HRESULT_FROM_WIN32(error));
    return QString::number(info.dwVolumeSerialNumber) + ":" + QString::number((quint64(info.nFileIndexHigh) << 32) | info.nFileIndexLow);
}
/** @brief 完了通知と取消しを収集する。寿命はPerformOperationsを囲むスタックが所有する。 */
class Sink final : public IFileOperationProgressSink {
public:
    CancelFlag cancel;
    QJsonObject receipt;
    QString restoreTarget;
    bool completed = false;
    HRESULT error = S_OK;
    ULONG refs = 1;
    /** @brief COMの型照会。 @param iid 型。 @param out 出力。 @return 結果。 */
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid, void** out) override {
        if (!out) return E_POINTER; *out = nullptr;
        if (iid != IID_IUnknown && iid != IID_IFileOperationProgressSink) return E_NOINTERFACE;
        *out = this; AddRef(); return S_OK;
    }
    /** @brief 参照数を増やす。 @return 数。 */
    ULONG STDMETHODCALLTYPE AddRef() override { return ++refs; }
    /** @brief 参照数のみ減らす。 @return 数。 */
    ULONG STDMETHODCALLTYPE Release() override { return --refs; }
    /** @brief 中断判定。 @return HRESULT。 */
    HRESULT check() const { return cancel && cancel->load() ? HRESULT_FROM_WIN32(ERROR_CANCELLED) : S_OK; }
    /** @brief 開始。 @return 継続可否。 */
    HRESULT STDMETHODCALLTYPE StartOperations() override { return check(); }
    /** @brief 最終エラーを保持。 @param hr 結果。 @return 通知受付。 */
    HRESULT STDMETHODCALLTYPE FinishOperations(HRESULT hr) override { if (FAILED(hr)) error = hr; return S_OK; }
    /** @brief リネーム前。 @param flags フラグ。 @param source 元。 @param target 名前。 @return 可否。 */
    HRESULT STDMETHODCALLTYPE PreRenameItem(DWORD flags, IShellItem* source, LPCWSTR target) override { return check(); }
    /** @brief リネーム後。 @param flags フラグ。 @param source 元。 @param target 名前。 @param hr 結果。 @param created 新項目。 @return 受付。 */
    HRESULT STDMETHODCALLTYPE PostRenameItem(DWORD flags, IShellItem* source, LPCWSTR target, HRESULT hr, IShellItem* created) override { return FinishOperations(hr); }
    /** @brief 復元の衝突を直前拒否。 @param flags フラグ。 @param source 元。 @param folder 先。 @param target 名前。 @return 可否。 */
    HRESULT STDMETHODCALLTYPE PreMoveItem(DWORD flags, IShellItem* source, IShellItem* folder, LPCWSTR target) override {
        if ((flags & 2) || QFileInfo::exists(restoreTarget)) return E_FAIL; return check();
    }
    /** @brief 移動完了を記録。 @param flags フラグ。 @param source 元。 @param folder 先。 @param target 名前。 @param hr 結果。 @param created 結果項目。 @return 受付。 */
    HRESULT STDMETHODCALLTYPE PostMoveItem(DWORD flags, IShellItem* source, IShellItem* folder, LPCWSTR target, HRESULT hr, IShellItem* created) override { completed = SUCCEEDED(hr); return FinishOperations(hr); }
    /** @brief コピー前。 @param flags フラグ。 @param source 元。 @param folder 先。 @param target 名前。 @return 可否。 */
    HRESULT STDMETHODCALLTYPE PreCopyItem(DWORD flags, IShellItem* source, IShellItem* folder, LPCWSTR target) override { return check(); }
    /** @brief コピー後。 @param flags フラグ。 @param source 元。 @param folder 先。 @param target 名前。 @param hr 結果。 @param created 新項目。 @return 受付。 */
    HRESULT STDMETHODCALLTYPE PostCopyItem(DWORD flags, IShellItem* source, IShellItem* folder, LPCWSTR target, HRESULT hr, IShellItem* created) override { return FinishOperations(hr); }
    /** @brief 完全削除への切替を拒否。 @param flags Shell操作。 @param source 対象。 @return 可否。 */
    HRESULT STDMETHODCALLTYPE PreDeleteItem(DWORD flags, IShellItem* source) override { return (flags & 0x80) ? check() : E_FAIL; }
    /** @brief ごみ箱の正確な項目を保持。 @param flags フラグ。 @param source 元。 @param hr 結果。 @param created ごみ箱項目。 @return 受付。 */
    HRESULT STDMETHODCALLTYPE PostDeleteItem(DWORD flags, IShellItem* source, HRESULT hr, IShellItem* created) override {
        if (FAILED(hr) || !created) { error = FAILED(hr) ? hr : E_FAIL; return error; }
        try {
            const auto physical = name(created, SIGDN_FILESYSPATH);
            receipt = {{"physicalPath", physical}, {"parsingName", name(created, SIGDN_DESKTOPABSOLUTEPARSING)}, {"identity", identity(physical)}};
            const QFileInfo recycled(physical);
            if (recycled.fileName().startsWith("$R") && QDir::fromNativeSeparators(physical).contains("/$Recycle.Bin/", Qt::CaseInsensitive)) {
                const auto metadata = recycled.dir().filePath("$I" + recycled.fileName().mid(2));
                if (QFileInfo(metadata).isFile()) { receipt["metadataPath"] = metadata; receipt["metadataIdentity"] = identity(metadata); }
            }
            completed = true;
        } catch (...) { error = E_FAIL; }
        return error;
    }
    /** @brief 作成前。 @param flags フラグ。 @param folder 親。 @param target 名前。 @return 可否。 */
    HRESULT STDMETHODCALLTYPE PreNewItem(DWORD flags, IShellItem* folder, LPCWSTR target) override { return check(); }
    /** @brief 作成後。 @param flags フラグ。 @param folder 親。 @param target 名前。 @param templ 雛形。 @param attrs 属性。 @param hr 結果。 @param created 新項目。 @return 受付。 */
    HRESULT STDMETHODCALLTYPE PostNewItem(DWORD flags, IShellItem* folder, LPCWSTR target, LPCWSTR templ, DWORD attrs, HRESULT hr, IShellItem* created) override { return FinishOperations(hr); }
    /** @brief 進捗。 @param total 全量。 @param done 処理量。 @return 可否。 */
    HRESULT STDMETHODCALLTYPE UpdateProgress(UINT total, UINT done) override { return check(); }
    /** @brief タイマー初期化。 @return 可否。 */
    HRESULT STDMETHODCALLTYPE ResetTimer() override { return check(); }
    /** @brief タイマー中断。 @return 可否。 */
    HRESULT STDMETHODCALLTYPE PauseTimer() override { return check(); }
    /** @brief タイマー再開。 @return 可否。 */
    HRESULT STDMETHODCALLTYPE ResumeTimer() override { return check(); }
};
/** @brief Shell操作を同期実行する。 @param source 元。 @param sink 通知。 @param folder 復元先、nullは削除。 @param target 名前。 */
void perform(IShellItem* source, Sink& sink, IShellItem* folder = nullptr, const QString& target = {}) {
    ComPtr<IFileOperation> op;
    checked(CoCreateInstance(CLSID_FileOperation, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&op)));
    // 復元にYes-to-allを付けるとShellが上書きフラグを立てるため、復元は確認省略しない。
    checked(op->SetOperationFlags(folder ? (FOF_NOERRORUI | FOF_SILENT | FOFX_EARLYFAILURE)
        : (FOF_NOCONFIRMATION | FOF_NOERRORUI | FOF_SILENT | FOF_WANTNUKEWARNING | FOFX_RECYCLEONDELETE | FOFX_EARLYFAILURE)));
    if (folder) checked(op->MoveItem(source, folder, reinterpret_cast<LPCWSTR>(target.utf16()), &sink));
    else checked(op->DeleteItem(source, &sink));
    const auto hr = op->PerformOperations();
    if (sink.completed) return;
    checked(sink.error); checked(hr); throw std::runtime_error("Shell did not complete. Check Recycle Bin before retrying.");
}
}
QJsonObject recyclePath(const QString& path, const CancelFlag& cancel) {
    Apartment apartment; Sink sink; sink.cancel = cancel; auto source = item(path); perform(source.Get(), sink); return sink.receipt;
}
void validateRecycled(const QJsonObject& receipt, const QString& path) {
    const QString physical = receipt.value("physicalPath").toString();
    if (identity(physical) != receipt.value("identity").toString() || QFileInfo::exists(path))
        throw std::runtime_error("Recycle Bin item changed or restore destination exists");
    const auto parent = QFileInfo(path).absolutePath();
    if (identity(parent).section(':', 0, 0) != receipt.value("identity").toString().section(':', 0, 0))
        throw std::runtime_error("Restore destination volume changed");
}
void restoreRecycled(const QJsonObject& receipt, const QString& path) {
    validateRecycled(receipt, path);
    const auto physical = receipt.value("physicalPath").toString(); const auto parent = QFileInfo(path).absolutePath();
    Apartment apartment;
    auto bin = item("shell:RecycleBinFolder"); ComPtr<IEnumShellItems> children;
    checked(bin->BindToHandler(nullptr, BHID_EnumItems, IID_PPV_ARGS(&children)));
    ComPtr<IShellItem> match;
    while (true) {
        ComPtr<IShellItem> child; ULONG fetched = 0; checked(children->Next(1, &child, &fetched)); if (!fetched) break;
        try { if (QString::compare(name(child.Get(), SIGDN_FILESYSPATH), physical, Qt::CaseInsensitive) == 0) { match = child; break; } } catch (...) {}
    }
    if (!match) throw std::runtime_error("Item is no longer in Recycle Bin");
    if (identity(name(match.Get(), SIGDN_FILESYSPATH)) != receipt.value("identity").toString()) throw std::runtime_error("Recycle Bin identity changed");
    auto destination = item(parent); Sink sink; sink.restoreTarget = path;
    perform(match.Get(), sink, destination.Get(), QFileInfo(path).fileName());
    // 一部Shell環境で残る削除管理票だけを、作成時のIDと照合して掃除する。
    // 復元した実ファイルや他のごみ箱項目には触れない。掃除失敗で復元を再試行させない。
    const auto metadata = receipt.value("metadataPath").toString(); const QFileInfo recycled(physical);
    if (!metadata.isEmpty() && recycled.fileName().startsWith("$R") && QDir::fromNativeSeparators(physical).contains("/$Recycle.Bin/", Qt::CaseInsensitive)
        && QDir::cleanPath(metadata) == QDir::cleanPath(recycled.dir().filePath("$I" + recycled.fileName().mid(2)))
        && !QFileInfo::exists(physical) && QFileInfo::exists(path)) {
        try { if (identity(metadata) == receipt.value("metadataIdentity").toString()) QFile::remove(metadata); } catch (...) {}
    }
}
}
