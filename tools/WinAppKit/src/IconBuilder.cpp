/**
 * @file IconBuilder.cpp
 * @brief SVGで描いたアイコンから、Windowsのアイコンファイル(.ico)を作るコマンドラインツール。
 *
 * 使い方:
 * @code
 * IconBuilder.exe --svg FramePlayer.svg --svg-for 16,20=FramePlayer-16.svg --svg-for 24=FramePlayer-24.svg
 *                 --sizes 16,20,24,32,40,48,64,256 --ico FramePlayer.ico --png-dir preview
 * @endcode
 *
 * SVGの描画はWindows標準のDirect2D(Windows 10 1703以降のSVG描画機能)、PNGへの変換はWIC
 * (Windows Imaging Component)で行う。外部のライブラリは使わない。
 * Direct2DのSVG描画は、SVGの機能の一部(図形・パス・塗り・線・変形など)に対応する。文字(text要素)や
 * CSSの細かな指定には対応しないので、アイコンは図形とパスだけで描くこと。
 *
 * .icoには、サイズごとにPNGの画像を入れる(Windows Vista以降の形式)。小さいサイズは、細部を省いて画素の升目で
 * 描いた別のSVG(--svg-for)から作れる。縮めると潰れる細かい形を描かず、輪郭をにじませないため
 * (例: viewBox="0 0 16 16" で座標1つが16pxの1画素になるように描く)。
 */
#include <windows.h>
#include <d2d1_3.h>
#include <shlwapi.h>
#include <wincodec.h>
#include <wrl/client.h>

#include <algorithm>
#include <clocale>
#include <cstdint>
#include <cstdio>
#include <cwchar>
#include <string>
#include <vector>

using Microsoft::WRL::ComPtr;

namespace {

/** @brief コマンドラインの指定。 */
struct Options {
    std::wstring svg;          ///< 既定で使うSVG(--svg-for で指定の無いサイズ)。
    std::vector<std::pair<int, std::wstring>> svgFor;  ///< サイズごとに使うSVG(--svg-for)。
    std::vector<int> sizes;    ///< 作るサイズ(ピクセル、1〜256)。
    std::wstring ico;          ///< 書き出す.icoのパス。
    std::wstring pngDir;       ///< サイズごとのPNGも書き出すフォルダ(空なら書き出さない)。
};

/**
 * @brief 失敗の理由を表示する。
 * @param message 理由。
 * @param hr 失敗したWindowsの呼び出しの結果(0なら出さない)。
 */
void printError(const wchar_t* message, HRESULT hr = S_OK) {
    if (FAILED(hr)) {
        std::fwprintf(stderr, L"IconBuilder: %ls (0x%08lX)\n", message, static_cast<unsigned long>(hr));
    } else {
        std::fwprintf(stderr, L"IconBuilder: %ls\n", message);
    }
}

/** @brief 使い方を表示する。 */
void printUsage() {
    std::fwprintf(stderr,
                  L"使い方: IconBuilder --svg <既定.svg> [--svg-for 16,20=<16px用.svg> ...]\n"
                  L"                    [--sizes 16,24,32,48,256] --ico <出力.ico> [--png-dir <フォルダ>]\n");
}

/**
 * @brief 「16,24,32」のようなサイズの並びを読む。
 * @param text 読む文字列。
 * @param sizes 読んだサイズの格納先(小さい順に並べ、重複を除く)。
 * @return すべて1〜256の数として読めればtrue。
 */
bool parseSizes(const std::wstring& text, std::vector<int>& sizes) {
    sizes.clear();
    std::size_t start = 0;
    while (start <= text.size()) {
        const std::size_t end = text.find(L',', start);
        const std::wstring part = text.substr(start, end == std::wstring::npos ? std::wstring::npos : end - start);
        wchar_t* stop = nullptr;
        const long value = std::wcstol(part.c_str(), &stop, 10);
        if (part.empty() || !stop || *stop != L'\0' || value < 1 || value > 256) {
            return false;
        }
        sizes.push_back(static_cast<int>(value));
        if (end == std::wstring::npos) {
            break;
        }
        start = end + 1;
    }
    std::sort(sizes.begin(), sizes.end());
    sizes.erase(std::unique(sizes.begin(), sizes.end()), sizes.end());
    return !sizes.empty();
}

/**
 * @brief コマンドラインを読む。
 * @param argc 引数の数。
 * @param argv 引数。
 * @param options 読んだ指定の格納先。
 * @return 必要な指定がそろっていればtrue。
 */
bool parseOptions(int argc, wchar_t** argv, Options& options) {
    options.sizes = {16, 20, 24, 32, 40, 48, 64, 256};  // Windowsが使う主なサイズ(拡大率100〜250%を含む)。
    for (int i = 1; i < argc; ++i) {
        const std::wstring name = argv[i];
        if (i + 1 >= argc) {
            return false;
        }
        const std::wstring value = argv[++i];
        if (name == L"--svg") {
            options.svg = value;
        } else if (name == L"--svg-for") {
            // 「16,20=パス」: 書いたサイズはそのSVGで作る(何度でも指定できる)。
            const std::size_t equal = value.find(L'=');
            std::vector<int> sizes;
            if (equal == std::wstring::npos || !parseSizes(value.substr(0, equal), sizes)) {
                return false;
            }
            for (int size : sizes) {
                options.svgFor.emplace_back(size, value.substr(equal + 1));
            }
        } else if (name == L"--sizes") {
            if (!parseSizes(value, options.sizes)) {
                return false;
            }
        } else if (name == L"--ico") {
            options.ico = value;
        } else if (name == L"--png-dir") {
            options.pngDir = value;
        } else {
            return false;
        }
    }
    return !options.svg.empty() && !options.ico.empty();
}

/** @brief SVGを描いてPNGにするための、Direct2DとWICの道具一式。 */
class Renderer {
public:
    /**
     * @brief Direct2DとWICの工場(オブジェクトを作る入口)を用意する。
     * @return 用意できればtrue。
     */
    bool initialize() {
        HRESULT hr = CoCreateInstance(CLSID_WICImagingFactory, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&wic_));
        if (FAILED(hr)) {
            printError(L"WICを使えません", hr);
            return false;
        }
        hr = D2D1CreateFactory(D2D1_FACTORY_TYPE_SINGLE_THREADED, IID_PPV_ARGS(&d2d_));
        if (FAILED(hr)) {
            printError(L"Direct2Dを使えません", hr);
            return false;
        }
        return true;
    }

    /**
     * @brief SVGを指定の大きさで描き、PNGのバイト列にする。
     * @param svgPath SVGファイルのパス。SVGの座標(viewBox)全体を、size x size に合わせて描く。
     * @param size 一辺のピクセル数。
     * @param png PNGのバイト列の格納先。
     * @return 成功ならtrue。
     */
    bool renderPng(const std::wstring& svgPath, int size, std::vector<std::uint8_t>& png) {
        // 描画先: 透明で初期化した、透明度付きの画像(色は透明度を掛けた形で持つ。Direct2Dの描画に必要な形)。
        ComPtr<IWICBitmap> bitmap;
        HRESULT hr = wic_->CreateBitmap(size, size, GUID_WICPixelFormat32bppPBGRA, WICBitmapCacheOnLoad, &bitmap);
        if (FAILED(hr)) {
            printError(L"画像を作れません", hr);
            return false;
        }
        const D2D1_RENDER_TARGET_PROPERTIES properties = D2D1::RenderTargetProperties(
            D2D1_RENDER_TARGET_TYPE_SOFTWARE, D2D1::PixelFormat(DXGI_FORMAT_B8G8R8A8_UNORM, D2D1_ALPHA_MODE_PREMULTIPLIED),
            96.0f, 96.0f);
        ComPtr<ID2D1RenderTarget> target;
        hr = d2d_->CreateWicBitmapRenderTarget(bitmap.Get(), properties, &target);
        // SVGの描画は、描画先の新しい形(ID2D1DeviceContext5)だけが持つ機能。
        ComPtr<ID2D1DeviceContext5> context;
        if (SUCCEEDED(hr)) {
            hr = target.As(&context);
        }
        if (FAILED(hr)) {
            printError(L"SVGを描ける描画先を作れません(Windows 10 1703以降が必要)", hr);
            return false;
        }
        ComPtr<IStream> svgStream;
        hr = SHCreateStreamOnFileEx(svgPath.c_str(), STGM_READ | STGM_SHARE_DENY_WRITE, FILE_ATTRIBUTE_NORMAL, FALSE,
                                    nullptr, &svgStream);
        if (FAILED(hr)) {
            printError((L"SVGを開けません: " + svgPath).c_str(), hr);
            return false;
        }
        ComPtr<ID2D1SvgDocument> document;
        hr = context->CreateSvgDocument(svgStream.Get(), D2D1::SizeF(static_cast<float>(size), static_cast<float>(size)),
                                        &document);
        if (FAILED(hr)) {
            printError((L"SVGを読めません(対応していない書き方があるかもしれません): " + svgPath).c_str(), hr);
            return false;
        }
        // SVGの width/height は描く大きさに合わせて上書きする(viewBoxの座標全体が size x size に収まる)。
        ComPtr<ID2D1SvgElement> root;
        document->GetRoot(&root);
        if (root) {
            const D2D1_SVG_LENGTH length{static_cast<float>(size), D2D1_SVG_LENGTH_UNITS_NUMBER};
            root->SetAttributeValue(L"width", length);
            root->SetAttributeValue(L"height", length);
        }
        context->BeginDraw();
        context->Clear(D2D1::ColorF(0, 0, 0, 0));
        context->DrawSvgDocument(document.Get());
        hr = context->EndDraw();
        if (FAILED(hr)) {
            printError(L"SVGを描けません", hr);
            return false;
        }
        return encodePng(bitmap.Get(), png);
    }

private:
    /**
     * @brief 画像をPNGのバイト列にする。
     * @param bitmap 描いた画像(透明度を掛けた形)。
     * @param png PNGのバイト列の格納先。
     * @return 成功ならtrue。
     * @note PNGとアイコンは透明度を掛けない形(普通の透明度付き)で持つので、変換してから書く。
     */
    bool encodePng(IWICBitmap* bitmap, std::vector<std::uint8_t>& png) {
        ComPtr<IWICBitmapSource> straight;
        HRESULT hr = WICConvertBitmapSource(GUID_WICPixelFormat32bppBGRA, bitmap, &straight);
        ComPtr<IStream> stream;
        if (SUCCEEDED(hr)) {
            hr = CreateStreamOnHGlobal(nullptr, TRUE, &stream);  // メモリ上に書く(後でバイト列として取り出す)。
        }
        ComPtr<IWICBitmapEncoder> encoder;
        if (SUCCEEDED(hr)) {
            hr = wic_->CreateEncoder(GUID_ContainerFormatPng, nullptr, &encoder);
        }
        if (SUCCEEDED(hr)) {
            hr = encoder->Initialize(stream.Get(), WICBitmapEncoderNoCache);
        }
        ComPtr<IWICBitmapFrameEncode> frame;
        if (SUCCEEDED(hr)) {
            hr = encoder->CreateNewFrame(&frame, nullptr);
        }
        if (SUCCEEDED(hr)) {
            hr = frame->Initialize(nullptr);
        }
        if (SUCCEEDED(hr)) {
            hr = frame->WriteSource(straight.Get(), nullptr);
        }
        if (SUCCEEDED(hr)) {
            hr = frame->Commit();
        }
        if (SUCCEEDED(hr)) {
            hr = encoder->Commit();
        }
        if (FAILED(hr)) {
            printError(L"PNGにできません", hr);
            return false;
        }
        // メモリ上に書いたPNGを取り出す。
        STATSTG stat{};
        stream->Stat(&stat, STATFLAG_NONAME);
        png.resize(static_cast<std::size_t>(stat.cbSize.QuadPart));
        const LARGE_INTEGER zero{};
        stream->Seek(zero, STREAM_SEEK_SET, nullptr);
        ULONG read = 0;
        stream->Read(png.data(), static_cast<ULONG>(png.size()), &read);
        return read == png.size();
    }

    ComPtr<IWICImagingFactory> wic_;
    ComPtr<ID2D1Factory1> d2d_;
};

/**
 * @brief バイト列をファイルに書く。
 * @param path 書き出すパス。
 * @param data 書く内容。
 * @return 書けたらtrue。
 */
bool writeFile(const std::wstring& path, const std::vector<std::uint8_t>& data) {
    FILE* file = nullptr;
    if (_wfopen_s(&file, path.c_str(), L"wb") != 0 || !file) {
        printError((L"書き出せません: " + path).c_str());
        return false;
    }
    const bool ok = std::fwrite(data.data(), 1, data.size(), file) == data.size();
    std::fclose(file);
    return ok;
}

/**
 * @brief サイズごとのPNGをまとめて.icoの形にする。
 * @param images サイズとPNGのバイト列の組(小さい順)。
 * @return .icoのバイト列。
 * @note .icoは「見出し(6バイト) + 画像ごとの目次(16バイトずつ) + 画像の中身」の並び。
 *       目次の幅・高さは1バイトなので、256は0と書く決まり。
 */
std::vector<std::uint8_t> buildIco(const std::vector<std::pair<int, std::vector<std::uint8_t>>>& images) {
    std::vector<std::uint8_t> ico;
    auto put16 = [&](std::uint16_t v) {
        ico.push_back(static_cast<std::uint8_t>(v & 0xFF));
        ico.push_back(static_cast<std::uint8_t>(v >> 8));
    };
    auto put32 = [&](std::uint32_t v) {
        for (int i = 0; i < 4; ++i) {
            ico.push_back(static_cast<std::uint8_t>((v >> (8 * i)) & 0xFF));
        }
    };
    put16(0);  // 予約。
    put16(1);  // 種類: 1 = アイコン。
    put16(static_cast<std::uint16_t>(images.size()));
    std::uint32_t offset = static_cast<std::uint32_t>(6 + 16 * images.size());
    for (const auto& [size, png] : images) {
        ico.push_back(static_cast<std::uint8_t>(size >= 256 ? 0 : size));  // 幅。
        ico.push_back(static_cast<std::uint8_t>(size >= 256 ? 0 : size));  // 高さ。
        ico.push_back(0);                                                // 色数(256色より多いなら0)。
        ico.push_back(0);                                                // 予約。
        put16(1);                                                        // 色の面の数。
        put16(32);                                                       // 1画素あたりのビット数。
        put32(static_cast<std::uint32_t>(png.size()));
        put32(offset);
        offset += static_cast<std::uint32_t>(png.size());
    }
    for (const auto& image : images) {
        ico.insert(ico.end(), image.second.begin(), image.second.end());
    }
    return ico;
}

}  // namespace

/**
 * @brief ツールの入口。指定のサイズごとにSVGを描いてPNGにし、.icoにまとめて書き出す。
 * @param argc 引数の数。
 * @param argv 引数。
 * @return 成功なら0、使い方の誤りなら1、作れなかったら2。
 */
int wmain(int argc, wchar_t** argv) {
    // 日本語のメッセージを、コンソールにもパイプ(ビルドの記録など)にもUTF-8で出す。
    std::setlocale(LC_ALL, ".UTF-8");
    Options options;
    if (!parseOptions(argc, argv, options)) {
        printUsage();
        return 1;
    }
    if (FAILED(CoInitializeEx(nullptr, COINIT_MULTITHREADED))) {
        printError(L"COMを初期化できません");
        return 2;
    }
    int result = 0;
    {
        Renderer renderer;
        std::vector<std::pair<int, std::vector<std::uint8_t>>> images;
        if (!renderer.initialize()) {
            result = 2;
        }
        for (int size : options.sizes) {
            if (result != 0) {
                break;
            }
            std::wstring svg = options.svg;
            for (const auto& [forSize, path] : options.svgFor) {
                if (forSize == size) {
                    svg = path;
                }
            }
            std::vector<std::uint8_t> png;
            if (!renderer.renderPng(svg, size, png)) {
                result = 2;
                break;
            }
            if (!options.pngDir.empty()) {
                CreateDirectoryW(options.pngDir.c_str(), nullptr);  // 既にあれば何もしない。
                if (!writeFile(options.pngDir + L"\\" + std::to_wstring(size) + L".png", png)) {
                    result = 2;
                    break;
                }
            }
            const std::size_t slash = svg.find_last_of(L"\\/");
            std::wprintf(L"%3d px  %ls  %zu bytes\n", size,
                         slash == std::wstring::npos ? svg.c_str() : svg.c_str() + slash + 1, png.size());
            images.emplace_back(size, std::move(png));
        }
        if (result == 0 && !writeFile(options.ico, buildIco(images))) {
            result = 2;
        }
        if (result == 0) {
            std::wprintf(L"書き出しました: %ls\n", options.ico.c_str());
        }
    }
    CoUninitialize();
    return result;
}
