/**
 * @file SetupUi.cpp
 * @brief セットアップの画面の実装。
 */
#include "setup/SetupUi.h"

#include "setup/Common.h"

#include <commctrl.h>
#include <shobjidl.h>
#include <wrl/client.h>

#include <algorithm>
#include <atomic>
#include <mutex>
#include <thread>

namespace wak {

namespace {

/**
 * @brief このexeに入っているアプリのアイコン(リソースの1番)を読む。
 * @return アイコン。無ければnullptr。
 */
HICON appIcon() {
    HICON icon = nullptr;
    LoadIconMetric(GetModuleHandleW(nullptr), MAKEINTRESOURCEW(1), LIM_LARGE, &icon);
    return icon;
}

/**
 * @brief ダイアログの共通の設定をする(アイコン・文字・ボタン)。
 * @param config 設定の格納先。
 * @param spec 中身。
 * @param buttons ボタンの一覧の格納先(configが指すので、ダイアログを閉じるまで残す)。
 */
void fillConfig(TASKDIALOGCONFIG& config, const DialogSpec& spec, std::vector<TASKDIALOG_BUTTON>& buttons) {
    config.cbSize = sizeof(config);
    config.hInstance = GetModuleHandleW(nullptr);
    config.dwFlags = TDF_ALLOW_DIALOG_CANCELLATION | TDF_POSITION_RELATIVE_TO_WINDOW | TDF_SIZE_TO_CONTENT;
    config.pszWindowTitle = spec.title.c_str();
    config.pszMainInstruction = spec.instruction.c_str();
    config.pszContent = spec.content.empty() ? nullptr : spec.content.c_str();
    switch (spec.icon) {
    case DialogIcon::App:
        if (HICON icon = appIcon()) {
            config.dwFlags |= TDF_USE_HICON_MAIN;
            config.hMainIcon = icon;
        } else {
            config.pszMainIcon = TD_INFORMATION_ICON;
        }
        break;
    case DialogIcon::Information:
        config.pszMainIcon = TD_INFORMATION_ICON;
        break;
    case DialogIcon::Warning:
        config.pszMainIcon = TD_WARNING_ICON;
        break;
    case DialogIcon::Error:
        config.pszMainIcon = TD_ERROR_ICON;
        break;
    }
    for (const auto& [id, text] : spec.buttons) {
        buttons.push_back({id, text.c_str()});
    }
    config.cButtons = static_cast<UINT>(buttons.size());
    config.pButtons = buttons.empty() ? nullptr : buttons.data();
    config.nDefaultButton = spec.defaultButton != 0 ? spec.defaultButton : (buttons.empty() ? 0 : buttons[0].nButtonID);
    config.dwCommonButtons = (spec.cancelButton ? TDCBF_CANCEL_BUTTON : 0) | (spec.closeButton ? TDCBF_CLOSE_BUTTON : 0);
    if (!spec.verification.empty()) {
        config.pszVerificationText = spec.verification.c_str();
        if (spec.verificationChecked) {
            config.dwFlags |= TDF_VERIFICATION_FLAG_CHECKED;
        }
    }
}

/**
 * @brief ダイアログからの知らせ(リンクが押されたなど)を受ける。
 * @param hwnd ダイアログ。
 * @param notification 知らせの種類。
 * @param wParam 知らせごとの値。
 * @param lParam 知らせごとの値(リンクならhrefの文字列)。
 * @param data showDialogに渡した中身(DialogSpec)。
 * @return S_OK。
 */
HRESULT CALLBACK dialogCallback(HWND hwnd, UINT notification, WPARAM wParam, LPARAM lParam, LONG_PTR data) {
    (void)hwnd;
    (void)wParam;
    const auto* spec = reinterpret_cast<const DialogSpec*>(data);
    if (notification == TDN_HYPERLINK_CLICKED && spec && spec->onLink) {
        spec->onLink(reinterpret_cast<const wchar_t*>(lParam));
    }
    return S_OK;
}

/** @brief 進み具合のダイアログと、作業のスレッドで共有する状態。 */
struct ProgressState {
    std::atomic<int> percent{0};     ///< 進み具合(0〜100)。
    std::atomic<bool> done{false};   ///< 作業が終わったか。
    std::mutex mutex;                ///< stepを守る。
    std::wstring step;               ///< 今の作業の説明。
    std::wstring shownStep;          ///< ダイアログに出している説明(UIのスレッドだけが使う)。
};

/**
 * @brief 進み具合のダイアログの知らせを受ける。タイマーで進み具合を写し、作業が終わったら閉じる。
 * @param hwnd ダイアログ。
 * @param notification 知らせの種類。
 * @param wParam 知らせごとの値。
 * @param lParam 知らせごとの値。
 * @param data 共有の状態(ProgressState)。
 * @return 作業中にボタンで閉じようとしたらS_FALSE(閉じない)。それ以外はS_OK。
 */
HRESULT CALLBACK progressCallback(HWND hwnd, UINT notification, WPARAM wParam, LPARAM lParam, LONG_PTR data) {
    (void)lParam;
    auto* state = reinterpret_cast<ProgressState*>(data);
    switch (notification) {
    case TDN_CREATED:
        SendMessageW(hwnd, TDM_ENABLE_BUTTON, IDCANCEL, FALSE);  // 作業中は閉じられないようにする。
        SendMessageW(hwnd, TDM_SET_PROGRESS_BAR_RANGE, 0, MAKELPARAM(0, 100));
        break;
    case TDN_TIMER: {
        SendMessageW(hwnd, TDM_SET_PROGRESS_BAR_POS, state->percent.load(), 0);
        std::wstring step;
        {
            std::lock_guard<std::mutex> lock(state->mutex);
            step = state->step;
        }
        if (step != state->shownStep) {
            state->shownStep = step;
            SendMessageW(hwnd, TDM_SET_ELEMENT_TEXT, TDE_CONTENT, reinterpret_cast<LPARAM>(state->shownStep.c_str()));
        }
        if (state->done) {
            SendMessageW(hwnd, TDM_ENABLE_BUTTON, IDCANCEL, TRUE);
            PostMessageW(hwnd, TDM_CLICK_BUTTON, IDCANCEL, 0);
        }
        break;
    }
    case TDN_BUTTON_CLICKED:
        return (wParam == IDCANCEL && !state->done) ? S_FALSE : S_OK;
    default:
        break;
    }
    return S_OK;
}

constexpr int kFirstExtensionId = 1000;  ///< 関連付けの画面: 拡張子のチェックボックスの最初の番号。
constexpr int kSelectAllId = 200;        ///< 「すべて選択」。
constexpr int kSelectNoneId = 201;       ///< 「すべて解除」。
constexpr int kContextMenuId = 202;      ///< 「右クリックに追加」。
constexpr int kExtensionColumns = 4;     ///< 拡張子のチェックボックスを並べる列の数。

/**
 * @brief ダイアログの定義(DLGTEMPLATE)をメモリ上で組み立てる。リソースファイルを使わずにダイアログを作るため。
 * @note 定義は2バイト単位の並びで、各部品の定義は4バイト境界から始める決まり(DLGITEMTEMPLATEの形)。
 *       寸法の単位はダイアログ単位(書体の大きさに比例する単位)なので、画面の拡大率が変わっても崩れない。
 */
class TemplateBuilder {
public:
    /**
     * @brief ダイアログ本体の定義を始める。
     * @param title ウィンドウのタイトル。
     * @param width 幅(ダイアログ単位)。
     * @param height 高さ(ダイアログ単位)。
     */
    void begin(const std::wstring& title, short width, short height) {
        putDword(DS_SETFONT | DS_MODALFRAME | DS_CENTER | WS_POPUP | WS_CAPTION | WS_SYSMENU);
        putDword(0);         // 拡張スタイル。
        data_.push_back(0);  // 部品の数(後で数える)。
        data_.push_back(0);  // x
        data_.push_back(0);  // y
        data_.push_back(static_cast<WORD>(width));
        data_.push_back(static_cast<WORD>(height));
        data_.push_back(0);  // メニューなし。
        data_.push_back(0);  // 標準のダイアログの種類。
        putString(title);
        data_.push_back(9);  // 書体の大きさ(ポイント)。
        putString(L"Segoe UI");
    }

    /**
     * @brief 部品を1つ足す。
     * @param style 部品のスタイル(WS_CHILD などは自分で付ける)。
     * @param x 左(ダイアログ単位)。
     * @param y 上(ダイアログ単位)。
     * @param width 幅(ダイアログ単位)。
     * @param height 高さ(ダイアログ単位)。
     * @param id 部品の番号。
     * @param kind 部品の種類(0x0080=ボタン類、0x0082=文字)。
     * @param text 文字。
     */
    void item(DWORD style, short x, short y, short width, short height, WORD id, WORD kind, const std::wstring& text) {
        if (data_.size() % 2 != 0) {
            data_.push_back(0);  // 4バイト境界に揃える。
        }
        putDword(style | WS_CHILD | WS_VISIBLE);
        putDword(0);
        data_.push_back(static_cast<WORD>(x));
        data_.push_back(static_cast<WORD>(y));
        data_.push_back(static_cast<WORD>(width));
        data_.push_back(static_cast<WORD>(height));
        data_.push_back(id);
        data_.push_back(0xFFFF);  // 種類は番号で指定する。
        data_.push_back(kind);
        putString(text);
        data_.push_back(0);  // 追加のデータなし。
        ++data_[4];          // 部品の数を数える。
    }

    /**
     * @brief 組み立てた定義を返す。
     * @return DialogBoxIndirectParamに渡す定義。
     */
    const DLGTEMPLATE* get() const { return reinterpret_cast<const DLGTEMPLATE*>(data_.data()); }

private:
    /**
     * @brief 4バイトの数を足す。
     * @param value 数。
     */
    void putDword(DWORD value) {
        data_.push_back(LOWORD(value));
        data_.push_back(HIWORD(value));
    }

    /**
     * @brief 文字列を、終わりの0まで足す。
     * @param text 文字列。
     */
    void putString(const std::wstring& text) {
        data_.insert(data_.end(), text.begin(), text.end());
        data_.push_back(0);
    }

    std::vector<WORD> data_;
};

/**
 * @brief 「右クリックに追加」は、関連付ける拡張子が1つも無いときは選べないようにする。
 * @param dialog ダイアログ。
 * @param choice 選択の内容(候補の数を知るため)。
 */
void updateAssociationControls(HWND dialog, const AssociationChoice& choice) {
    bool any = false;
    for (std::size_t i = 0; i < choice.extensions.size(); ++i) {
        any = any || IsDlgButtonChecked(dialog, kFirstExtensionId + static_cast<int>(i)) == BST_CHECKED;
    }
    EnableWindow(GetDlgItem(dialog, kContextMenuId), any);
}

/**
 * @brief 関連付けの画面の処理。
 * @param dialog ダイアログ。
 * @param message メッセージの種類。
 * @param wParam メッセージごとの値。
 * @param lParam メッセージごとの値(作ったときは選択の内容)。
 * @return 処理したらTRUE。
 */
INT_PTR CALLBACK associationProc(HWND dialog, UINT message, WPARAM wParam, LPARAM lParam) {
    auto* choice = reinterpret_cast<AssociationChoice*>(GetWindowLongPtrW(dialog, DWLP_USER));
    switch (message) {
    case WM_INITDIALOG:
        SetWindowLongPtrW(dialog, DWLP_USER, lParam);
        choice = reinterpret_cast<AssociationChoice*>(lParam);
        for (std::size_t i = 0; i < choice->extensions.size(); ++i) {
            CheckDlgButton(dialog, kFirstExtensionId + static_cast<int>(i), choice->selected[i] ? BST_CHECKED : BST_UNCHECKED);
            if (!choice->available.empty() && !choice->available[i]) {
                // 前提の拡張機能が入っていない拡張子は、選べないようにする(灰色)。
                EnableWindow(GetDlgItem(dialog, kFirstExtensionId + static_cast<int>(i)), FALSE);
            }
        }
        CheckDlgButton(dialog, kContextMenuId, choice->contextMenu ? BST_CHECKED : BST_UNCHECKED);
        updateAssociationControls(dialog, *choice);
        return TRUE;
    case WM_COMMAND: {
        const int id = LOWORD(wParam);
        if (id == kSelectAllId || id == kSelectNoneId) {
            for (std::size_t i = 0; i < choice->extensions.size(); ++i) {
                const bool available = choice->available.empty() || choice->available[i];
                CheckDlgButton(dialog, kFirstExtensionId + static_cast<int>(i),
                               id == kSelectAllId && available ? BST_CHECKED : BST_UNCHECKED);
            }
            updateAssociationControls(dialog, *choice);
            return TRUE;
        }
        if (id >= kFirstExtensionId && id < kFirstExtensionId + static_cast<int>(choice->extensions.size())) {
            updateAssociationControls(dialog, *choice);
            return TRUE;
        }
        if (id == IDOK) {
            for (std::size_t i = 0; i < choice->extensions.size(); ++i) {
                choice->selected[i] = IsDlgButtonChecked(dialog, kFirstExtensionId + static_cast<int>(i)) == BST_CHECKED;
            }
            choice->contextMenu = IsDlgButtonChecked(dialog, kContextMenuId) == BST_CHECKED;
            EndDialog(dialog, IDOK);
            return TRUE;
        }
        if (id == IDCANCEL) {
            EndDialog(dialog, IDCANCEL);
            return TRUE;
        }
        break;
    }
    default:
        break;
    }
    return FALSE;
}

}  // namespace

bool chooseAssociations(const std::wstring& title, const std::wstring& appName, AssociationChoice& choice) {
    constexpr WORD kButton = 0x0080;
    constexpr WORD kStatic = 0x0082;
    constexpr short kWidth = 270;
    constexpr short kMargin = 8;
    TemplateBuilder builder;
    const int rows = static_cast<int>((choice.extensions.size() + kExtensionColumns - 1) / kExtensionColumns);
    short y = 8;
    const short gridTop = 34;
    const short afterGrid = static_cast<short>(gridTop + rows * 13 + 4);
    // 選べない拡張子の説明(あるときだけ)。行ごとに、半角を1・全角を2として幅を数え、折り返した行数を見積もる
    // (ダイアログの単位で、半角1文字はおよそ4。幅254に半角で約60文字。余裕を見て56で折り返すとする)。
    const bool hasNote = !choice.unavailableNote.empty();
    int noteLines = 0;
    for (const std::wstring& line : split(choice.unavailableNote, L'\n')) {
        int units = 0;
        for (wchar_t c : line) {
            units += c < 0x0100 ? 1 : 2;
        }
        noteLines += std::max(1, (units + 55) / 56);
    }
    const short noteTop = static_cast<short>(afterGrid + 20);
    const short noteHeight = hasNote ? static_cast<short>(noteLines * 9 + 2) : 0;
    const short contextTop = static_cast<short>(noteTop + (hasNote ? noteHeight + 6 : 0));
    const short buttonsTop = static_cast<short>(contextTop + (choice.hasContextMenu ? 20 : 0));
    builder.begin(title, kWidth, static_cast<short>(buttonsTop + 22));
    builder.item(SS_LEFT, kMargin, y, kWidth - 2 * kMargin, 24, static_cast<WORD>(-1), kStatic,
                 L"Choose the file types to open with " + appName +
                     L". They are added to \"Open with\", where you can also make it the default app.");
    for (std::size_t i = 0; i < choice.extensions.size(); ++i) {
        const short column = static_cast<short>(i % kExtensionColumns);
        const short row = static_cast<short>(i / kExtensionColumns);
        builder.item(BS_AUTOCHECKBOX | WS_TABSTOP, static_cast<short>(kMargin + 4 + column * 62),
                     static_cast<short>(gridTop + row * 13), 58, 11, static_cast<WORD>(kFirstExtensionId + i), kButton,
                     choice.extensions[i]);
    }
    builder.item(BS_PUSHBUTTON | WS_TABSTOP, kMargin + 4, afterGrid, 58, 14, kSelectAllId, kButton, L"Select All");
    builder.item(BS_PUSHBUTTON | WS_TABSTOP, kMargin + 66, afterGrid, 58, 14, kSelectNoneId, kButton, L"Clear All");
    if (hasNote) {
        builder.item(SS_LEFT, kMargin, noteTop, kWidth - 2 * kMargin, noteHeight, static_cast<WORD>(-1), kStatic,
                     choice.unavailableNote);
    }
    if (choice.hasContextMenu) {
        builder.item(BS_AUTOCHECKBOX | WS_TABSTOP, kMargin, contextTop, kWidth - 2 * kMargin, 11, kContextMenuId, kButton,
                     L"Add \"Open with " + appName + L"\" to the right-click menu");
    }
    builder.item(BS_DEFPUSHBUTTON | WS_TABSTOP, kWidth - kMargin - 50 - 4 - 50, buttonsTop, 50, 14, IDOK, kButton, L"OK");
    builder.item(BS_PUSHBUTTON | WS_TABSTOP, kWidth - kMargin - 50, buttonsTop, 50, 14, IDCANCEL, kButton, L"Cancel");
    AssociationChoice edited = choice;
    const INT_PTR result = DialogBoxIndirectParamW(GetModuleHandleW(nullptr), builder.get(), GetActiveWindow(),
                                                   &associationProc, reinterpret_cast<LPARAM>(&edited));
    if (result != IDOK) {
        return false;
    }
    choice = edited;
    return true;
}

DialogResult showDialog(const DialogSpec& spec) {
    TASKDIALOGCONFIG config{};
    std::vector<TASKDIALOG_BUTTON> buttons;
    fillConfig(config, spec, buttons);
    if (spec.onLink) {
        config.dwFlags |= TDF_ENABLE_HYPERLINKS;
    }
    if (spec.commandLinks) {
        config.dwFlags |= TDF_USE_COMMAND_LINKS;
    }
    config.pfCallback = &dialogCallback;
    config.lpCallbackData = reinterpret_cast<LONG_PTR>(&spec);
    DialogResult result;
    BOOL verification = FALSE;
    if (FAILED(TaskDialogIndirect(&config, &result.button, nullptr, &verification))) {
        result.button = IDCANCEL;
    }
    result.verification = verification != FALSE;
    if (config.dwFlags & TDF_USE_HICON_MAIN) {
        DestroyIcon(config.hMainIcon);
    }
    return result;
}

void runWithProgress(const std::wstring& title, const std::wstring& instruction,
                     const std::function<void(const std::function<void(int, const std::wstring&)>&)>& work) {
    ProgressState state;
    std::thread worker([&] {
        // 作業のスレッドでもCOMを使う(ショートカットの作成などはCOMの部品)。
        const HRESULT com = CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
        work([&](int percent, const std::wstring& step) {
            state.percent = percent;
            std::lock_guard<std::mutex> lock(state.mutex);
            state.step = step;
        });
        if (SUCCEEDED(com)) {
            CoUninitialize();
        }
        state.done = true;
    });
    DialogSpec spec;
    spec.title = title;
    spec.instruction = instruction;
    spec.content = L" ";
    spec.cancelButton = true;
    TASKDIALOGCONFIG config{};
    std::vector<TASKDIALOG_BUTTON> buttons;
    fillConfig(config, spec, buttons);
    config.dwFlags |= TDF_SHOW_PROGRESS_BAR | TDF_CALLBACK_TIMER;
    config.dwFlags &= ~TDF_ALLOW_DIALOG_CANCELLATION;  // Escや×で閉じない。
    config.pfCallback = &progressCallback;
    config.lpCallbackData = reinterpret_cast<LONG_PTR>(&state);
    int button = 0;
    TaskDialogIndirect(&config, &button, nullptr, nullptr);
    worker.join();
    if (config.dwFlags & TDF_USE_HICON_MAIN) {
        DestroyIcon(config.hMainIcon);
    }
}

std::wstring chooseFolder(const std::wstring& title, const std::wstring& initial) {
    Microsoft::WRL::ComPtr<IFileOpenDialog> dialog;
    if (FAILED(CoCreateInstance(CLSID_FileOpenDialog, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&dialog)))) {
        return std::wstring();
    }
    DWORD options = 0;
    dialog->GetOptions(&options);
    dialog->SetOptions(options | FOS_PICKFOLDERS | FOS_FORCEFILESYSTEM);
    dialog->SetTitle(title.c_str());
    Microsoft::WRL::ComPtr<IShellItem> folder;
    if (SUCCEEDED(SHCreateItemFromParsingName(initial.c_str(), nullptr, IID_PPV_ARGS(&folder)))) {
        dialog->SetFolder(folder.Get());
    }
    if (FAILED(dialog->Show(nullptr))) {
        return std::wstring();
    }
    Microsoft::WRL::ComPtr<IShellItem> item;
    PWSTR path = nullptr;
    if (FAILED(dialog->GetResult(&item)) || FAILED(item->GetDisplayName(SIGDN_FILESYSPATH, &path))) {
        return std::wstring();
    }
    std::wstring result = path;
    CoTaskMemFree(path);
    return result;
}

}  // namespace wak
