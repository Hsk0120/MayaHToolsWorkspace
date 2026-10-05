/**
 * @file image_convert.cpp
 * @brief 確認用の画像を、Windows標準のWICで別の形式に書き直す道具(FramePlayerImageConvert、配布対象外)。
 *
 * ffmpegやoiiotoolで作れない形式(HEIF・JPEG XL・JPEG XR)の確認用画像を作るために使う。
 * 出力の形式は拡張子で決まる(Windowsに入っているWICのエンコーダーを使う)。
 *
 * 使い方: FramePlayerImageConvert <入力> <出力> [--float]
 *         FramePlayerImageConvert <入力.exr> --time   (EXRの読み込みの速さを測る)
 *   --float  浮動小数点(半精度のRGBA)で書く(JPEG XRだけ。値はリニアとして書かれる)。
 * 入力も出力もEXRのときは、FramePlayerのEXRの読み込み(readExr)で読み、圧縮なしのRGBAの半精度のEXRで書く
 * (自前の読み込みの結果を、oiiotool --diff で元のファイルと比べるため)。
 * 終了コード: 0=成功、1=失敗。
 */
#include <windows.h>
#include <objbase.h>
#include <wincodec.h>
#include <wrl/client.h>

#include <chrono>
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <cwchar>
#include <fstream>
#include <string>

#include "core/ExrReader.h"

using Microsoft::WRL::ComPtr;

namespace {

/**
 * @brief 文字列を小文字にした拡張子(「.exr」など)を返す。
 * @param path パス。
 * @return 拡張子(無ければ空)。
 */
std::wstring extensionOf(const std::wstring& path) {
    const std::size_t dot = path.find_last_of(L'.');
    std::wstring extension = dot == std::wstring::npos ? std::wstring() : path.substr(dot);
    for (wchar_t& c : extension) {
        c = static_cast<wchar_t>(towlower(c));
    }
    return extension;
}

/**
 * @brief EXRをFramePlayerの読み込みで読み、圧縮なしのRGBAの半精度のEXRで書く。
 * @param input 入力のEXR。
 * @param output 出力のEXR。
 * @return 終了コード(0=成功、1=失敗)。
 */
int exrToPlainExr(const std::wstring& input, const std::wstring& output) {
    frameplayer::ExrImage image;
    std::wstring error;
    if (!frameplayer::readExr(input, image, error)) {
        std::fwprintf(stderr, L"EXRを読めません: %ls\n", error.c_str());
        return 1;
    }
    std::string header;
    auto put32 = [](std::string& out, std::uint32_t v) {
        for (int i = 0; i < 4; ++i) {
            out.push_back(static_cast<char>((v >> (8 * i)) & 0xFF));
        }
    };
    auto attribute = [&](const char* name, const char* type, const std::string& data) {
        header += name;
        header.push_back('\0');
        header += type;
        header.push_back('\0');
        put32(header, static_cast<std::uint32_t>(data.size()));
        header += data;
    };
    // チャンネルの一覧は名前の順(A・B・G・R)。各チャンネルは半精度(1)、間引きなし。
    std::string channels;
    for (const char* name : {"A", "B", "G", "R"}) {
        channels += name;
        channels.push_back('\0');
        put32(channels, 1);
        channels += std::string(4, '\0');
        put32(channels, 1);
        put32(channels, 1);
    }
    channels.push_back('\0');
    std::string box;
    put32(box, 0);
    put32(box, 0);
    put32(box, static_cast<std::uint32_t>(image.width - 1));
    put32(box, static_cast<std::uint32_t>(image.height - 1));
    attribute("channels", "chlist", channels);
    attribute("compression", "compression", std::string(1, '\0'));
    attribute("dataWindow", "box2i", box);
    attribute("displayWindow", "box2i", box);
    attribute("lineOrder", "lineOrder", std::string(1, '\0'));
    std::string aspect(4, '\0');
    std::memcpy(aspect.data(), &image.pixelAspect, 4);
    attribute("pixelAspectRatio", "float", aspect);
    attribute("screenWindowCenter", "v2f", std::string(8, '\0'));
    const float one = 1.0f;
    std::string width(4, '\0');
    std::memcpy(width.data(), &one, 4);
    attribute("screenWindowWidth", "float", width);
    header.push_back('\0');

    std::string file;
    put32(file, 20000630);
    put32(file, 2);
    file += header;
    const std::size_t lineBytes = static_cast<std::size_t>(image.width) * 2 * 4;
    const std::size_t start = file.size() + 8 * static_cast<std::size_t>(image.height);
    for (int y = 0; y < image.height; ++y) {
        const std::uint64_t offset = start + static_cast<std::size_t>(y) * (8 + lineBytes);
        put32(file, static_cast<std::uint32_t>(offset & 0xFFFFFFFF));
        put32(file, static_cast<std::uint32_t>(offset >> 32));
    }
    static constexpr int kOrder[] = {3, 2, 1, 0};  // A・B・G・R の順に、RGBAの何番目かを並べる。
    for (int y = 0; y < image.height; ++y) {
        put32(file, static_cast<std::uint32_t>(y));
        put32(file, static_cast<std::uint32_t>(lineBytes));
        for (int channel : kOrder) {
            for (int x = 0; x < image.width; ++x) {
                const std::uint16_t v = image.pixels[(static_cast<std::size_t>(y) * image.width + x) * 4 + channel];
                file.push_back(static_cast<char>(v & 0xFF));
                file.push_back(static_cast<char>(v >> 8));
            }
        }
    }
    std::ofstream out(output, std::ios::binary);
    out.write(file.data(), static_cast<std::streamsize>(file.size()));
    return out ? 0 : 1;
}

}  // namespace

int wmain(int argc, wchar_t** argv) {
    if (argc < 3) {
        std::fwprintf(stderr, L"使い方: FramePlayerImageConvert <入力> <出力> [--float]\n");
        return 1;
    }
    const std::wstring output = argv[2];
    if (extensionOf(argv[1]) == L".exr" && output == L"--time") {
        // 読み込みの速さを測る(5回読んだ平均。書き出しはしない)。
        const auto start = std::chrono::steady_clock::now();
        for (int i = 0; i < 5; ++i) {
            frameplayer::ExrImage image;
            std::wstring error;
            if (!frameplayer::readExr(argv[1], image, error)) {
                std::fwprintf(stderr, L"EXRを読めません: %ls\n", error.c_str());
                return 1;
            }
        }
        const double ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - start).count();
        std::wprintf(L"%.1f ms\n", ms / 5);
        return 0;
    }
    if (extensionOf(argv[1]) == L".exr" && extensionOf(output) == L".exr") {
        return exrToPlainExr(argv[1], output);
    }
    CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    const bool floating = argc > 3 && std::wcscmp(argv[3], L"--float") == 0;
    ComPtr<IWICImagingFactory> factory;
    ComPtr<IWICBitmapDecoder> decoder;
    ComPtr<IWICBitmapFrameDecode> source;
    HRESULT hr = CoCreateInstance(CLSID_WICImagingFactory, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&factory));
    if (SUCCEEDED(hr)) {
        hr = factory->CreateDecoderFromFilename(argv[1], nullptr, GENERIC_READ, WICDecodeMetadataCacheOnDemand, &decoder);
    }
    if (SUCCEEDED(hr)) {
        hr = decoder->GetFrame(0, &source);
    }
    // 出力の拡張子に合うエンコーダーを探す。
    const std::wstring extension = extensionOf(output);
    GUID container{};
    bool found = false;
    ComPtr<IEnumUnknown> encoders;
    if (SUCCEEDED(hr)) {
        hr = factory->CreateComponentEnumerator(WICEncoder, WICComponentEnumerateDefault, &encoders);
    }
    ComPtr<IUnknown> item;
    ULONG fetched = 0;
    while (SUCCEEDED(hr) && !found && encoders->Next(1, &item, &fetched) == S_OK) {
        ComPtr<IWICBitmapCodecInfo> info;
        wchar_t extensions[256] = {};
        UINT length = 0;
        if (SUCCEEDED(item.As(&info)) && SUCCEEDED(info->GetFileExtensions(256, extensions, &length))) {
            std::wstring list = extensions;
            for (wchar_t& c : list) {
                c = static_cast<wchar_t>(towlower(c));
            }
            list += L",";
            if (list.find(extension + L",") != std::wstring::npos) {
                info->GetContainerFormat(&container);
                found = true;
            }
        }
    }
    if (FAILED(hr) || !found) {
        std::fwprintf(stderr, L"変換できません(入力を読めない、または出力の形式のエンコーダーが無い)\n");
        return 1;
    }
    ComPtr<IWICStream> stream;
    ComPtr<IWICBitmapEncoder> encoder;
    ComPtr<IWICBitmapFrameEncode> frame;
    ComPtr<IPropertyBag2> properties;
    hr = factory->CreateStream(&stream);
    if (SUCCEEDED(hr)) {
        hr = stream->InitializeFromFilename(output.c_str(), GENERIC_WRITE);
    }
    if (SUCCEEDED(hr)) {
        hr = factory->CreateEncoder(container, nullptr, &encoder);
    }
    if (SUCCEEDED(hr)) {
        hr = encoder->Initialize(stream.Get(), WICBitmapEncoderNoCache);
    }
    if (SUCCEEDED(hr)) {
        hr = encoder->CreateNewFrame(&frame, &properties);
    }
    if (SUCCEEDED(hr) && properties) {
        // 劣化を小さくする(対応していない形式では無視される)。
        PROPBAG2 option{};
        option.pstrName = const_cast<LPOLESTR>(L"ImageQuality");
        VARIANT value;
        VariantInit(&value);
        value.vt = VT_R4;
        value.fltVal = 1.0f;
        properties->Write(1, &option, &value);
        // 可逆で書ける形式(JPEG XR・JPEG XLなど)は可逆にする(確認用の画像に圧縮の劣化を入れないため)。
        option.pstrName = const_cast<LPOLESTR>(L"Lossless");
        VariantInit(&value);
        value.vt = VT_BOOL;
        value.boolVal = VARIANT_TRUE;
        properties->Write(1, &option, &value);
    }
    if (SUCCEEDED(hr)) {
        hr = frame->Initialize(properties.Get());
    }
    UINT width = 0;
    UINT height = 0;
    if (SUCCEEDED(hr)) {
        hr = source->GetSize(&width, &height);
    }
    if (SUCCEEDED(hr)) {
        hr = frame->SetSize(width, height);
    }
    WICPixelFormatGUID format = floating ? GUID_WICPixelFormat64bppRGBAHalf : GUID_WICPixelFormat24bppBGR;
    if (SUCCEEDED(hr)) {
        hr = frame->SetPixelFormat(&format);  // エンコーダーが対応する近い形式に変わる。
    }
    ComPtr<IWICFormatConverter> converter;
    if (SUCCEEDED(hr)) {
        hr = factory->CreateFormatConverter(&converter);
    }
    if (SUCCEEDED(hr)) {
        hr = converter->Initialize(source.Get(), format, WICBitmapDitherTypeNone, nullptr, 0.0, WICBitmapPaletteTypeCustom);
    }
    if (SUCCEEDED(hr)) {
        hr = frame->WriteSource(converter.Get(), nullptr);
    }
    if (SUCCEEDED(hr)) {
        hr = frame->Commit();
    }
    if (SUCCEEDED(hr)) {
        hr = encoder->Commit();
    }
    if (FAILED(hr)) {
        std::fwprintf(stderr, L"書き込みに失敗しました (HRESULT 0x%08lX)\n", static_cast<unsigned long>(hr));
        return 1;
    }
    return 0;
}
