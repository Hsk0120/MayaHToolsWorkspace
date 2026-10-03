/**
 * @file SetupUi.cpp
 * @brief セットアップの画面の実装。
 */
#include "setup/SetupUi.h"

#include <commctrl.h>
#include <shobjidl.h>
#include <wrl/client.h>

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

}  // namespace

DialogResult showDialog(const DialogSpec& spec) {
    TASKDIALOGCONFIG config{};
    std::vector<TASKDIALOG_BUTTON> buttons;
    fillConfig(config, spec, buttons);
    if (spec.onLink) {
        config.dwFlags |= TDF_ENABLE_HYPERLINKS;
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
