/**
 * @file Requirements.cpp
 * @brief 関連付けの前提条件を調べる処理の実装。
 */
#include "setup/Requirements.h"

#include <windows.h>
#include <mfapi.h>
#include <mfidl.h>
#include <mftransform.h>
#include <objbase.h>
#include <wincodec.h>
#include <wrl/client.h>

#include <cwctype>
#include <vector>

#include "setup/Common.h"

using Microsoft::WRL::ComPtr;

namespace wak {

namespace {

/**
 * @brief WICの画像コーデック(デコーダー)のどれかが、その拡張子を読めるかを調べる。
 * @param extension 拡張子(「.heic」の形)。
 * @return 読めるならtrue。
 * @note コーデックが宣言している拡張子の一覧(GetFileExtensions)と比べる。ストアの拡張機能で入るコーデックも含まれる。
 */
bool hasWicDecoder(const std::wstring& extension) {
    ComPtr<IWICImagingFactory> factory;
    if (FAILED(CoCreateInstance(CLSID_WICImagingFactory, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&factory)))) {
        return false;
    }
    ComPtr<IEnumUnknown> decoders;
    if (FAILED(factory->CreateComponentEnumerator(WICDecoder, WICComponentEnumerateDefault, &decoders))) {
        return false;
    }
    ComPtr<IUnknown> item;
    ULONG fetched = 0;
    while (decoders->Next(1, &item, &fetched) == S_OK) {
        ComPtr<IWICBitmapCodecInfo> info;
        UINT length = 0;
        if (FAILED(item.As(&info)) || FAILED(info->GetFileExtensions(0, nullptr, &length)) || length == 0) {
            continue;
        }
        std::vector<wchar_t> list(length);
        if (FAILED(info->GetFileExtensions(length, list.data(), &length))) {
            continue;
        }
        for (const std::wstring& candidate : split(list.data(), L',')) {
            if (equalsIgnoreCase(candidate, extension)) {
                return true;
            }
        }
    }
    return false;
}

/**
 * @brief その形式のMedia Foundationの動画デコーダーがあるかを調べる。
 * @param fourcc 形式の4文字(HEVC・AV01・VP90など)。
 * @return あればtrue。
 * @note ソフトウェアとハードウェアの両方、ストアの拡張機能で入るデコーダーも含めて探す。
 */
bool hasMfVideoDecoder(const std::wstring& fourcc) {
    if (fourcc.size() != 4) {
        return false;
    }
    // 動画の形式のGUIDは、FOURCCを先頭の32bitに入れた決まった形(MFVideoFormat_Base)。
    GUID subtype = MFVideoFormat_Base;
    subtype.Data1 = static_cast<DWORD>(fourcc[0] & 0xFF) | (static_cast<DWORD>(fourcc[1] & 0xFF) << 8) |
                    (static_cast<DWORD>(fourcc[2] & 0xFF) << 16) | (static_cast<DWORD>(fourcc[3] & 0xFF) << 24);
    MFT_REGISTER_TYPE_INFO input{MFMediaType_Video, subtype};
    IMFActivate** activates = nullptr;
    UINT32 count = 0;
    const HRESULT hr = MFTEnumEx(MFT_CATEGORY_VIDEO_DECODER, MFT_ENUM_FLAG_ALL, &input, nullptr, &activates, &count);
    if (SUCCEEDED(hr)) {
        for (UINT32 i = 0; i < count; ++i) {
            activates[i]->Release();
        }
        CoTaskMemFree(activates);
    }
    return SUCCEEDED(hr) && count > 0;
}

/**
 * @brief 条件の項を1つ調べる。
 * @param extension 対象の拡張子。
 * @param term 項(wic・wic:.ext・mfvideo:FOURCC)。
 * @param valid 項の書き方が正しくなければfalseにする。
 * @return 満たしていればtrue。
 */
bool meetsTerm(const std::wstring& extension, const std::wstring& term, bool& valid) {
    if (equalsIgnoreCase(term, L"wic")) {
        return hasWicDecoder(extension);
    }
    const std::size_t colon = term.find(L':');
    const std::wstring kind = colon == std::wstring::npos ? term : term.substr(0, colon);
    const std::wstring value = colon == std::wstring::npos ? std::wstring() : term.substr(colon + 1);
    if (equalsIgnoreCase(kind, L"wic") && value.size() >= 2 && value[0] == L'.') {
        return hasWicDecoder(value);
    }
    if (equalsIgnoreCase(kind, L"mfvideo") && value.size() == 4) {
        std::wstring upper = value;
        for (wchar_t& c : upper) {
            c = static_cast<wchar_t>(std::towupper(c));
        }
        return hasMfVideoDecoder(upper);
    }
    valid = false;
    return false;
}

}  // namespace

bool meetsRequirement(const std::wstring& extension, const std::wstring& expression, std::wstring& missing) {
    missing.clear();
    if (expression.empty()) {
        return true;
    }
    const HRESULT com = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    const HRESULT mf = MFStartup(MF_VERSION, MFSTARTUP_LITE);
    bool all = true;
    for (const std::wstring& group : split(expression, L'+')) {
        bool any = false;
        bool valid = true;
        for (const std::wstring& term : split(group, L'|')) {
            any = any || meetsTerm(extension, term, valid);
        }
        if (!any || !valid) {
            all = false;
            missing += (missing.empty() ? L"" : L" + ") + group;
        }
    }
    if (SUCCEEDED(mf)) {
        MFShutdown();
    }
    if (SUCCEEDED(com)) {
        CoUninitialize();
    }
    return all;
}

bool isValidRequirement(const std::wstring& expression) {
    for (const std::wstring& group : split(expression, L'+')) {
        const std::vector<std::wstring> terms = split(group, L'|');
        if (terms.empty()) {
            return false;
        }
        for (const std::wstring& term : terms) {
            const std::size_t colon = term.find(L':');
            const std::wstring kind = colon == std::wstring::npos ? term : term.substr(0, colon);
            const std::wstring value = colon == std::wstring::npos ? std::wstring() : term.substr(colon + 1);
            const bool ok = (equalsIgnoreCase(kind, L"wic") && (colon == std::wstring::npos ||
                                                                 (value.size() >= 2 && value[0] == L'.'))) ||
                            (equalsIgnoreCase(kind, L"mfvideo") && value.size() == 4);
            if (!ok) {
                return false;
            }
        }
    }
    return true;
}

}  // namespace wak
