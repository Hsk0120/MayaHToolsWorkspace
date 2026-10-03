/**
 * @file Ui.cpp
 * @brief 操作部のGDIの描画部品の実装。
 */
#include "app/Ui.h"

#include <dwmapi.h>

#include <algorithm>

namespace frameplayer::ui {

namespace {

constexpr DWORD kDwmUseImmersiveDarkMode = 20;  ///< DWMWA_USE_IMMERSIVE_DARK_MODE(古いSDKに無い場合があるので番号で持つ)。
constexpr DWORD kDwmCaptionColor = 35;          ///< DWMWA_CAPTION_COLOR(Windows 11以降)。
constexpr DWORD kDwmTextColor = 36;             ///< DWMWA_TEXT_COLOR(Windows 11以降)。

/**
 * @brief Windows 11の標準の文字(Segoe UI Variable)が使えるか調べる。
 * @return 使えればtrue。結果は最初の1回だけ調べて覚えておく。
 */
bool hasVariableFont() {
    static const bool found = [] {
        HDC dc = GetDC(nullptr);
        LOGFONTW query{};
        query.lfCharSet = DEFAULT_CHARSET;
        wcscpy_s(query.lfFaceName, L"Segoe UI Variable Text");
        bool exists = false;
        EnumFontFamiliesExW(
            dc, &query,
            [](const LOGFONTW*, const TEXTMETRICW*, DWORD, LPARAM param) -> int {
                *reinterpret_cast<bool*>(param) = true;
                return 0;
            },
            reinterpret_cast<LPARAM>(&exists), 0);
        ReleaseDC(nullptr, dc);
        return exists;
    }();
    return found;
}

}  // namespace

void fill(HDC dc, const RECT& rect, COLORREF color) {
    SetDCBrushColor(dc, color);
    FillRect(dc, &rect, static_cast<HBRUSH>(GetStockObject(DC_BRUSH)));
}

void frame(HDC dc, const RECT& rect, COLORREF color) {
    SetDCBrushColor(dc, color);
    FrameRect(dc, &rect, static_cast<HBRUSH>(GetStockObject(DC_BRUSH)));
}

HFONT createFont(int points, int dpi) {
    return CreateFontW(-MulDiv(points, dpi, 72), 0, 0, 0, FW_NORMAL, FALSE, FALSE, FALSE, DEFAULT_CHARSET,
                       OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY, DEFAULT_PITCH,
                       hasVariableFont() ? L"Segoe UI Variable Text" : L"Segoe UI");
}

void applyDarkTitleBar(HWND hwnd) {
    const BOOL dark = TRUE;
    DwmSetWindowAttribute(hwnd, kDwmUseImmersiveDarkMode, &dark, sizeof(dark));
    const COLORREF caption = kSurface;
    DwmSetWindowAttribute(hwnd, kDwmCaptionColor, &caption, sizeof(caption));
    const COLORREF text = kText;
    DwmSetWindowAttribute(hwnd, kDwmTextColor, &text, sizeof(text));
}

void drawRoundButton(HDC dc, const RECT& rect, COLORREF face, COLORREF border, COLORREF ink, const wchar_t* text,
                     int radius) {
    // 地と枠は、描画先に備わっている色を変えられるブラシとペンで描く(作成と破棄を省く)。
    HGDIOBJ oldBrush = SelectObject(dc, GetStockObject(DC_BRUSH));
    HGDIOBJ oldPen = SelectObject(dc, GetStockObject(DC_PEN));
    SetDCBrushColor(dc, face);
    SetDCPenColor(dc, border);
    RoundRect(dc, rect.left, rect.top, rect.right, rect.bottom, radius, radius);
    SelectObject(dc, oldBrush);
    SelectObject(dc, oldPen);
    SetTextColor(dc, ink);
    RECT textRect = rect;
    DrawTextW(dc, text, -1, &textRect, DT_CENTER | DT_VCENTER | DT_SINGLELINE);
}

void drawTransportIcon(HDC dc, const RECT& box, TransportIcon icon, COLORREF ink) {
    // 記号は箱の中央に、箱の大きさに合わせて描く。三角はPolygon、縦棒は四角で描く。
    const int cx = (box.left + box.right) / 2;
    const int cy = (box.top + box.bottom) / 2;
    const int h = std::max(3, static_cast<int>((box.bottom - box.top) / 4));  // 記号の高さの半分。
    const int bar = std::max(2, h / 3);
    HGDIOBJ oldBrush = SelectObject(dc, GetStockObject(DC_BRUSH));
    HGDIOBJ oldPen = SelectObject(dc, GetStockObject(DC_PEN));
    SetDCBrushColor(dc, ink);
    SetDCPenColor(dc, ink);
    auto triangleRight = [&](int left) {  // 右向きの三角(幅h)。
        const POINT p[] = {{left, cy - h}, {left, cy + h}, {left + h, cy}};
        Polygon(dc, p, 3);
    };
    auto triangleLeft = [&](int right) {  // 左向きの三角(幅h)。
        const POINT p[] = {{right, cy - h}, {right, cy + h}, {right - h, cy}};
        Polygon(dc, p, 3);
    };
    auto verticalBar = [&](int left) { fill(dc, RECT{left, cy - h, left + bar, cy + h + 1}, ink); };
    switch (icon) {
    case TransportIcon::Play: {
        const int w = h * 3 / 2;
        const POINT p[] = {{cx - w / 2, cy - h - 1}, {cx - w / 2, cy + h + 1}, {cx + w - w / 2, cy}};
        Polygon(dc, p, 3);
        break;
    }
    case TransportIcon::Pause:
        fill(dc, RECT{cx - h + 1, cy - h, cx - h + 1 + bar + 1, cy + h + 1}, ink);
        fill(dc, RECT{cx + h - bar - 1, cy - h, cx + h, cy + h + 1}, ink);
        break;
    case TransportIcon::Start:  // |◀◀
        verticalBar(cx - h - bar);
        triangleLeft(cx);
        triangleLeft(cx + h);
        break;
    case TransportIcon::Previous:  // |◀
        verticalBar(cx - h / 2 - bar);
        triangleLeft(cx + h / 2);
        break;
    case TransportIcon::Next:  // ▶|
        triangleRight(cx - h / 2);
        verticalBar(cx + h / 2 + 1);
        break;
    case TransportIcon::End:  // ▶▶|
        triangleRight(cx - h);
        triangleRight(cx);
        verticalBar(cx + h + 1);
        break;
    }
    SelectObject(dc, oldBrush);
    SelectObject(dc, oldPen);
}

HFONT FontCache::get(int points, int dpi) {
    if (dpi != dpi_) {
        clear();
        dpi_ = dpi;
    }
    for (const auto& [size, font] : fonts_) {
        if (size == points) {
            return font;
        }
    }
    HFONT font = createFont(points, dpi);
    fonts_.emplace_back(points, font);
    return font;
}

void FontCache::clear() {
    for (const auto& entry : fonts_) {
        DeleteObject(entry.second);
    }
    fonts_.clear();
}

Layer::~Layer() {
    if (dc_) {
        SelectObject(dc_, oldBitmap_);
        DeleteDC(dc_);
    }
    if (bitmap_) {
        DeleteObject(bitmap_);
    }
}

HDC Layer::prepare(HDC compatible, int width, int height) {
    width = std::max(1, width);
    height = std::max(1, height);
    if (!dc_) {
        dc_ = CreateCompatibleDC(compatible);
    }
    if (!bitmap_ || width != width_ || height != height_) {
        HBITMAP bitmap = CreateCompatibleBitmap(compatible, width, height);
        HGDIOBJ previous = SelectObject(dc_, bitmap);
        if (!bitmap_) {
            oldBitmap_ = previous;
        } else {
            DeleteObject(bitmap_);
        }
        bitmap_ = bitmap;
        width_ = width;
        height_ = height;
    }
    return dc_;
}

void Layer::blit(HDC target, int x, int y, int width, int height, int sourceX, int sourceY) const {
    if (dc_ && width > 0 && height > 0) {
        BitBlt(target, x, y, width, height, dc_, sourceX, sourceY, SRCCOPY);
    }
}

BackBuffer::~BackBuffer() {
    if (dc_) {
        SelectObject(dc_, oldBitmap_);
        DeleteDC(dc_);
    }
    if (bitmap_) {
        DeleteObject(bitmap_);
    }
}

HDC BackBuffer::begin(HDC screen, const RECT& area) {
    const int width = std::max(1L, area.right - area.left);
    const int height = std::max(1L, area.bottom - area.top);
    if (!dc_) {
        dc_ = CreateCompatibleDC(screen);
    }
    // 今の画像に入らないときだけ作り直す(ウィンドウを広げたときなど)。
    if (!bitmap_ || width > width_ || height > height_) {
        HBITMAP bitmap = CreateCompatibleBitmap(screen, std::max(width, width_), std::max(height, height_));
        HGDIOBJ previous = SelectObject(dc_, bitmap);
        if (!bitmap_) {
            oldBitmap_ = previous;
        } else {
            DeleteObject(bitmap_);
        }
        bitmap_ = bitmap;
        width_ = std::max(width, width_);
        height_ = std::max(height, height_);
    }
    area_ = area;
    SetViewportOrgEx(dc_, -area.left, -area.top, nullptr);
    return dc_;
}

void BackBuffer::present(HDC screen) {
    SetViewportOrgEx(dc_, 0, 0, nullptr);
    BitBlt(screen, area_.left, area_.top, area_.right - area_.left, area_.bottom - area_.top, dc_, 0, 0, SRCCOPY);
}

}  // namespace frameplayer::ui
