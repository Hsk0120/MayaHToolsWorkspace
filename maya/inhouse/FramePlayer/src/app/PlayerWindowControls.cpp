/**
 * @file PlayerWindowControls.cpp
 * @brief プレイヤーのメインウィンドウのうち、下部の操作部(タイムスライダー・レンジスライダー・数字の欄・
 *        移動/再生のボタン・音量)の配置・描画・マウスとキーの操作の実装。
 */
#include "app/PlayerWindow.h"

#include "core/Util.h"

#include "core/TraceLog.h"
#include "app/Ui.h"

#include <commctrl.h>
#include <uxtheme.h>
#include <windowsx.h>

#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cwchar>
#include <iterator>
#include <string>

namespace frameplayer {

PlayerWindow::Layout PlayerWindow::computeLayout() const {
    RECT client;
    GetClientRect(hwnd_, &client);
    const int dpi = static_cast<int>(GetDpiForWindow(hwnd_));
    const int left = static_cast<int>(client.left);
    const int right = static_cast<int>(client.right);
    const int bottom = static_cast<int>(client.bottom);
    // Mayaと同じく、下から「レンジスライダー」「タイムスライダー」の2段。映像はその上に余白なしで置く。
    const int rangeHeight = ui::scaled(36, dpi);
    const int timeHeight = ui::scaled(40, dpi);
    const int rangeTop = std::max(static_cast<int>(client.top), bottom - rangeHeight);
    const int timeTop = std::max(static_cast<int>(client.top), rangeTop - timeHeight);
    const int margin = ui::scaled(8, dpi);
    const int gap = ui::scaled(6, dpi);         // まとまりの中の間隔。
    const int groupGap = ui::scaled(16, dpi);   // まとまりどうしの間隔(範囲・動画の開始・fps・ボタン・音量)。
    const int fieldWidth = ui::scaled(64, dpi);
    const int fieldHeight = ui::scaled(24, dpi);  // 欄と文字のボタンは同じ高さに揃える。

    Layout layout;
    layout.video = {left, static_cast<int>(client.top), right, timeTop};
    layout.bar = {left, timeTop, right, bottom};
    layout.timeRow = {left, timeTop, right, rangeTop};
    layout.rangeRow = {left, rangeTop, right, bottom};

    // タイムスライダーの段: 左から目盛り、現在のフレームの欄、移動・再生のボタン(Mayaと同じ並び)。
    const int buttonSize = ui::scaled(26, dpi);
    const int buttonGap = ui::scaled(2, dpi);
    int x = right - margin - (buttonSize * 5 + buttonGap * 4);
    const int buttonsLeft = x;
    auto placeButton = [&] {
        const int top = timeTop + (timeHeight - buttonSize) / 2;
        const RECT r{x, top, x + buttonSize, top + buttonSize};
        x += buttonSize + buttonGap;
        return r;
    };
    layout.startButton = placeButton();
    layout.prevButton = placeButton();
    layout.button = placeButton();
    layout.nextButton = placeButton();
    layout.endButton = placeButton();
    const int timeFieldTop = timeTop + (timeHeight - fieldHeight) / 2;
    layout.currentField = {buttonsLeft - gap - fieldWidth, timeFieldTop, buttonsLeft - gap, timeFieldTop + fieldHeight};
    layout.ruler = {left + margin, timeTop + ui::scaled(4, dpi),
                    std::max(left + margin + 1, static_cast<int>(layout.currentField.left) - gap), rangeTop - ui::scaled(2, dpi)};

    // レンジスライダーの段(Mayaと同じ並び): 左から全体範囲の最初・再生範囲の最初の欄、バー、再生範囲の最後・
    // 全体範囲の最後の欄。その右に「動画の開始」の欄、fps、「Maya連携」「ファイル」「比較」、音量。
    const int rangeFieldTop = rangeTop + (rangeHeight - fieldHeight) / 2;
    auto fieldAt = [&](int fieldLeft) {
        return RECT{fieldLeft, rangeFieldTop, fieldLeft + fieldWidth, rangeFieldTop + fieldHeight};
    };
    layout.animStartField = fieldAt(left + margin);
    layout.playStartField = fieldAt(static_cast<int>(layout.animStartField.right) + gap);
    const int volumeWidth = ui::scaled(80, dpi);
    const int volumeHeight = ui::scaled(16, dpi);
    const int volumeTop = rangeTop + (rangeHeight - volumeHeight) / 2;
    layout.volumeSlider = {right - margin - volumeWidth, volumeTop, right - margin, volumeTop + volumeHeight};
    const int speakerSize = ui::scaled(22, dpi);
    const int speakerTop = rangeTop + (rangeHeight - speakerSize) / 2;
    const int speakerRight = static_cast<int>(layout.volumeSlider.left) - gap;
    layout.volumeButton = {speakerRight - speakerSize, speakerTop, speakerRight, speakerTop + speakerSize};
    const int textButtonHeight = fieldHeight;
    const int textButtonTop = rangeTop + (rangeHeight - textButtonHeight) / 2;
    const int compareRight = static_cast<int>(layout.volumeButton.left) - groupGap;
    layout.compareButton = {compareRight - ui::scaled(56, dpi), textButtonTop, compareRight, textButtonTop + textButtonHeight};
    const int fileRight = static_cast<int>(layout.compareButton.left) - gap;
    layout.fileButton = {fileRight - ui::scaled(72, dpi), textButtonTop, fileRight, textButtonTop + textButtonHeight};
    const int syncRight = static_cast<int>(layout.fileButton.left) - gap;
    layout.syncButton = {syncRight - ui::scaled(80, dpi), textButtonTop, syncRight, textButtonTop + textButtonHeight};
    const int rateRight = static_cast<int>(layout.syncButton.left) - groupGap;
    layout.rateLabel = {rateRight - ui::scaled(52, dpi), rangeTop, rateRight, bottom};
    layout.clipStartField = fieldAt(static_cast<int>(layout.rateLabel.left) - groupGap - fieldWidth);
    const int clipLabelRight = static_cast<int>(layout.clipStartField.left) - gap;
    layout.clipStartLabel = {clipLabelRight - ui::scaled(64, dpi), rangeTop, clipLabelRight, bottom};
    layout.animEndField = fieldAt(static_cast<int>(layout.clipStartLabel.left) - groupGap - fieldWidth);
    layout.playEndField = fieldAt(static_cast<int>(layout.animEndField.left) - gap - fieldWidth);
    layout.rangeBar = {static_cast<int>(layout.playStartField.right) + gap, rangeFieldTop,
                       std::max(static_cast<int>(layout.playStartField.right) + gap + 1,
                                static_cast<int>(layout.playEndField.left) - gap),
                       rangeFieldTop + fieldHeight};
    return layout;
}

void PlayerWindow::invalidateBar() {
    const RECT bar = computeLayout().bar;
    InvalidateRect(hwnd_, &bar, FALSE);
}

void PlayerWindow::invalidateTimeRow() {
    const RECT row = computeLayout().timeRow;
    InvalidateRect(hwnd_, &row, FALSE);
}

void PlayerWindow::paint() {
    const LONGLONG paintStart = nowTicks();
    PAINTSTRUCT ps;
    HDC screen = BeginPaint(hwnd_, &ps);
    const RECT area = ps.rcPaint;
    // 描き直す範囲を裏の画像に描いてから、一度に写す(ちらつき防止)。裏の画像は描き直しのたびに作らず使い回す。
    HDC dc = backBuffer_.begin(screen, area);
    ui::fill(dc, area, ui::kBackground);
    const int dpi = static_cast<int>(GetDpiForWindow(hwnd_));
    HGDIOBJ oldFont = SelectObject(dc, fonts_.get(14, dpi));
    SetBkMode(dc, TRANSPARENT);
    paintControls(dc, computeLayout(), dpi, area);
    SelectObject(dc, oldFont);
    backBuffer_.present(screen);
    EndPaint(hwnd_, &ps);
    traceLog("paint %lld us %ldx%ld", (nowTicks() - paintStart) * 1000000 / ticksPerSecond(), area.right - area.left,
            area.bottom - area.top);
}

void PlayerWindow::paintControls(HDC dc, const Layout& layout, int dpi, const RECT& area) {
    // 描き直す範囲にかかる段だけを描く(再生中はコマが進むたびに上段だけを描き直すため)。
    RECT overlap{};
    const bool timeRow = IntersectRect(&overlap, &area, &layout.timeRow) != FALSE;
    const bool rangeRow = IntersectRect(&overlap, &area, &layout.rangeRow) != FALSE;
    // 2段は、メディア プレーヤーと同じく1枚の地として塗る。
    ui::fill(dc, layout.bar, ui::kSurface);
    updateCacheRuns(layout);

    if (timeRow) {
        // 上段: 目盛り、現在のフレームの欄、移動・再生のボタン(枠なしの記号)。
        paintTimeSlider(dc, layout, dpi);
        paintField(dc, layout.currentField, currentSceneFrame(), Part::CurrentField, true, dpi);
        const COLORREF ink = clip_ ? ui::kText : ui::kDisabled;
        const int iconRadius = ui::scaled(6, dpi);
        const std::pair<Part, ui::TransportIcon> icons[] = {
            {Part::StartButton, ui::TransportIcon::Start},
            {Part::PrevButton, ui::TransportIcon::Previous},
            {Part::PlayButton, view_.isPlaying() ? ui::TransportIcon::Pause : ui::TransportIcon::Play},
            {Part::NextButton, ui::TransportIcon::Next},
            {Part::EndButton, ui::TransportIcon::End},
        };
        for (const auto& [part, icon] : icons) {
            const RECT box = partRect(layout, part);
            if (clip_ && hover_ == part) {
                // マウスが乗っている記号のボタンは、角を丸めた地を敷く(押せることを示す)。
                ui::drawRoundButton(dc, box, ui::kControlHover, ui::kControlHover, ink, L"", iconRadius);
            }
            ui::drawTransportIcon(dc, box, icon, ink);
        }
    }
    if (!rangeRow) {
        return;
    }

    // 下段: レンジスライダー、範囲の4つの欄、動画の開始の欄、fps、文字のボタン、音量。どの欄も入力できる。
    paintRangeSlider(dc, layout, dpi);
    // 全体範囲の欄は控えめに、再生範囲の欄は普通に描く(Mayaと同じ並びのまま、外側と内側を見分けやすくする)。
    const int start = settings_.startFrame;
    paintField(dc, layout.animStartField, start + animFirst_, Part::AnimStartField, false, dpi);
    paintField(dc, layout.playStartField, start + playFirst_, Part::PlayStartField, true, dpi);
    paintField(dc, layout.playEndField, start + playLast_, Part::PlayEndField, true, dpi);
    paintField(dc, layout.animEndField, start + animLast_, Part::AnimEndField, false, dpi);
    paintField(dc, layout.clipStartField, start, Part::ClipStartField, true, dpi);

    HGDIOBJ oldFont = SelectObject(dc, fonts_.get(ui::kTextPoints, dpi));
    SetTextColor(dc, clip_ ? ui::kSecondaryText : ui::kDisabled);
    RECT clipLabel = layout.clipStartLabel;
    DrawTextW(dc, L"動画の開始", -1, &clipLabel, DT_RIGHT | DT_VCENTER | DT_SINGLELINE);
    SetTextColor(dc, clip_ ? ui::kSecondaryText : ui::kDisabled);
    wchar_t rateText[32];
    std::swprintf(rateText, 32, L"%.4g fps", playbackRate());  // 書体は「動画の開始」と同じ(kTextPoints)。
    RECT rateRect = layout.rateLabel;
    DrawTextW(dc, rateText, -1, &rateRect, DT_CENTER | DT_VCENTER | DT_SINGLELINE);

    // 文字のボタン(「ファイル」「比較」)。角を丸めた薄い地と枠。比較中の「比較」は強調色の地に黒い文字にして、
    // 押すと比較をやめることを示す(メディア プレーヤーの「ファイルを開く」と同じ)。マウスが乗ったら明るくする。
    const int radius = ui::scaled(8, dpi);
    auto textButton = [&](Part part, const RECT& rect, bool accent, const wchar_t* text) {
        const bool hover = hover_ == part;
        if (accent) {
            const COLORREF face = hover ? ui::kAccentHover : ui::kAccent;
            ui::drawRoundButton(dc, rect, face, face, ui::kBackground, text, radius);
        } else {
            ui::drawRoundButton(dc, rect, hover ? ui::kControlHover : ui::kControlFace,
                                hover ? ui::kControlBorderHover : ui::kControlBorder, ui::kText, text, radius);
        }
    };
    textButton(Part::FileButton, layout.fileButton, false, L"ファイル ▾");
    // 「Maya連携」: 通常モードは薄い地。連携モードは強調色の地で、つながるまでは「連携待ち」、つながったら「連携中」。
    textButton(Part::SyncButton, layout.syncButton, syncServer_ != nullptr,
               !syncServer_ ? L"Maya連携" : syncServer_->connected() ? L"連携中" : L"連携待ち");
    textButton(Part::CompareButton, layout.compareButton, compareClip_ != nullptr, compareClip_ ? L"比較 ×" : L"比較");
    SelectObject(dc, oldFont);
    paintVolume(dc, layout, dpi);
}

void PlayerWindow::updateCacheRuns(const Layout& layout) {
    // キャッシュの有無は全コマ(1時間60fpsで21万6千)を調べるので、毎回の描画では計算し直さず、
    // 一定間隔(kCacheBarIntervalMs)ごと、または横幅や再生範囲が変わったときだけ計算する。
    if (!clip_) {
        return;
    }
    const LONGLONG now = nowTicks();
    const RECT& ruler = layout.ruler;
    const RECT& rangeBar = layout.rangeBar;
    if (cacheRunsTrack_.left == ruler.left && cacheRunsTrack_.right == ruler.right &&
        rangeCacheRunsBar_.left == rangeBar.left && rangeCacheRunsBar_.right == rangeBar.right &&
        cacheRunsFirst_ == playFirst_ && cacheRunsLast_ == playLast_ && cacheRunsAnimFirst_ == animFirst_ &&
        cacheRunsAnimLast_ == animLast_ && (now - lastCacheBarTicks_) * 1000 / ticksPerSecond() < kCacheBarIntervalMs) {
        return;
    }
    clip_->cachedFlags(cacheFlags_);
    lastCacheBarTicks_ = now;
    cacheRunsTrack_ = ruler;
    rangeCacheRunsBar_ = rangeBar;
    cacheRunsFirst_ = playFirst_;
    cacheRunsLast_ = playLast_;
    cacheRunsAnimFirst_ = animFirst_;
    cacheRunsAnimLast_ = animLast_;
    buildCacheRuns(cacheFlags_, playFirst_, playLast_, ruler.left, ruler.right - ruler.left, cacheRuns_);
    buildCacheRuns(cacheFlags_, animFirst_, animLast_, rangeBar.left, rangeBar.right - rangeBar.left,
                   rangeCacheRuns_);
}

void PlayerWindow::buildCacheRuns(const std::vector<std::uint8_t>& flags, int first, int last, int left, int width,
                                  std::vector<std::pair<int, int>>& runs) {
    // 横幅の各画素に割り当たるコマのうち、1つでもキャッシュにあれば塗る。動画の外のコマ(flagsの外)は調べない
    // (範囲がとても広いときに、1画素あたりの膨大なコマ数を数えないように)。
    runs.clear();
    const int count = last - first + 1;
    const int flagCount = static_cast<int>(flags.size());
    if (count <= 0 || width <= 0 || flags.empty()) {
        return;
    }
    int runStart = -1;
    for (int px = 0; px <= width; ++px) {
        bool cached = false;
        if (px < width) {
            const int f0 = first + static_cast<int>(static_cast<long long>(px) * count / width);
            const int f1 = std::max(f0 + 1, first + static_cast<int>(static_cast<long long>(px + 1) * count / width));
            const int end = std::min({f1, last + 1, flagCount});
            for (int i = std::max(f0, 0); i < end && !cached; ++i) {
                cached = flags[static_cast<std::size_t>(i)] != 0;
            }
        }
        if (cached && runStart < 0) {
            runStart = left + px;
        } else if (!cached && runStart >= 0) {
            runs.emplace_back(runStart, left + px);
            runStart = -1;
        }
    }
}

void PlayerWindow::paintRulerMarks(HDC dc, int width, int height, COLORREF slab, COLORREF outside, int dpi) {
    // 左上を(0, 0)として、地・細かい目盛り・数字の付く目盛りと数字を描く(作り置きの画像へ描く)。
    const int first = playFirst_;
    const int last = playLast_;
    const int count = last - first + 1;
    // 再生範囲の各コマに同じ幅の区画を割り当てる(Mayaと同じく、目盛りは区画の左端)。
    auto xOf = [&](int index) { return static_cast<int>(static_cast<long long>(index - first) * width / count); };
    // 地: 動画の外の区画は暗く塗り、動画のある所が分かるようにする。
    ui::fill(dc, RECT{0, 0, width, height}, outside);
    const int clipFirst = std::max(first, 0);
    const int clipLast = std::min(last, clip_ ? clip_->frameCount() - 1 : -1);
    if (clipFirst <= clipLast) {
        ui::fill(dc, RECT{xOf(clipFirst), 0, xOf(clipLast + 1), height}, slab);
    }
    const double pixelsPerFrame = static_cast<double>(width) / count;
    const int tickBottom = height - ui::scaled(kCacheStripHeight, dpi);

    // 数字の間隔は1・2・5・10・20・50…の中で、数字どうしが重ならない最小のもの。
    HGDIOBJ oldFont = SelectObject(dc, fonts_.get(ui::kSmallPoints, dpi));
    SetBkMode(dc, TRANSPARENT);
    wchar_t widest[32];
    std::swprintf(widest, 32, L"%d",
                  std::max(std::abs(settings_.startFrame + first), std::abs(settings_.startFrame + last)) * 10);
    SIZE labelSize{};
    GetTextExtentPoint32W(dc, widest, static_cast<int>(wcslen(widest)), &labelSize);
    const double minSpacing = labelSize.cx + ui::scaled(8, dpi);
    long long major = 1;
    for (long long base = 1; major * pixelsPerFrame < minSpacing && base < 100000000; base *= 10) {
        for (int multiplier : {1, 2, 5}) {
            major = base * multiplier;
            if (major * pixelsPerFrame >= minSpacing) {
                break;
            }
        }
    }
    // 細かい目盛りは、1コマごとに5ピクセル以上空くなら各コマ、そうでなければ数字の間隔の1/5か1/2。
    const double minTick = ui::scaled(5, dpi);
    long long minor = 0;
    if (pixelsPerFrame >= minTick) {
        minor = 1;
    } else if (major % 5 == 0 && (major / 5) * pixelsPerFrame >= minTick) {
        minor = major / 5;
    } else if (major % 2 == 0 && (major / 2) * pixelsPerFrame >= minTick) {
        minor = major / 2;
    }
    // 目盛りの番号はフレーム番号(開始フレームを足した番号)で揃える。
    const long long sceneFirst = static_cast<long long>(settings_.startFrame) + first;
    const long long sceneLast = static_cast<long long>(settings_.startFrame) + last;
    auto firstMultiple = [&](long long step) {
        const long long q = sceneFirst / step;
        const long long candidate = q * step;
        return candidate < sceneFirst ? candidate + step : candidate;
    };
    if (minor > 0) {
        for (long long frame = firstMultiple(minor); frame <= sceneLast; frame += minor) {
            const int x = xOf(static_cast<int>(frame - settings_.startFrame));
            ui::fill(dc, RECT{x, tickBottom - ui::scaled(5, dpi), x + 1, tickBottom}, ui::kTick);
        }
    }
    SetTextColor(dc, ui::kRulerText);
    for (long long frame = firstMultiple(major); frame <= sceneLast; frame += major) {
        const int x = xOf(static_cast<int>(frame - settings_.startFrame));
        ui::fill(dc, RECT{x, ui::scaled(2, dpi), x + 1, tickBottom}, ui::kMajorTick);
        wchar_t text[32];
        std::swprintf(text, 32, L"%lld", frame);
        // 右端で切れてしまう数字は描かない(途中で切れた数字は別の数に見えるため)。
        SIZE textSize{};
        GetTextExtentPoint32W(dc, text, static_cast<int>(wcslen(text)), &textSize);
        if (x + ui::scaled(3, dpi) + textSize.cx <= width) {
            RECT textRect{x + ui::scaled(3, dpi), ui::scaled(1, dpi), width, tickBottom};
            DrawTextW(dc, text, -1, &textRect, DT_LEFT | DT_TOP | DT_SINGLELINE);
        }
    }
    SelectObject(dc, oldFont);
}

void PlayerWindow::paintTimeSlider(HDC dc, const Layout& layout, int dpi) {
    const RECT& r = layout.ruler;
    const int width = r.right - r.left;
    const int height = r.bottom - r.top;
    if (width < 2) {
        return;
    }
    if (!clip_) {
        ui::fill(dc, r, ui::kRuler);
        return;
    }
    // 目盛り(線と数字)は、通常の地と現在のフレームの区画の色の地の2枚を作り置きしておく。
    // 描き直しでは2枚から写すだけにして、再生中に毎回すべての目盛りと数字を描かないようにする。
    // 作り置きは、横幅・高さ・再生範囲・開始フレーム・DPIのどれかが変わったときだけ作り直す。
    const RulerKey key{width, height, playFirst_, playLast_, settings_.startFrame, dpi, clip_->frameCount()};
    if (!(key == rulerKey_)) {
        paintRulerMarks(rulerLayer_.prepare(dc, width, height), width, height, ui::kRuler, ui::kRulerOutside, dpi);
        paintRulerMarks(rulerHighlightLayer_.prepare(dc, width, height), width, height, ui::kCurrentColumn,
                        ui::kCurrentColumn, dpi);
        rulerKey_ = key;
    }
    rulerLayer_.blit(dc, r.left, r.top, width, height, 0, 0);

    const int first = playFirst_;
    const int last = playLast_;
    const int count = last - first + 1;
    auto xOf = [&](int index) {
        return static_cast<int>(r.left) + static_cast<int>(static_cast<long long>(index - first) * width / count);
    };
    const int strip = ui::scaled(kCacheStripHeight, dpi);  // 下端のキャッシュの帯の高さ。
    const int tickBottom = r.bottom - strip;

    // 現在のフレームの区画は、区画の色の地で描いた作り置きから写す(目盛りが上に重なった見た目になる)。
    const bool currentInRange = current_ >= first && current_ <= last;
    int currentLeft = 0;
    int currentRight = 0;
    if (currentInRange) {
        currentLeft = xOf(current_);
        currentRight = std::max(currentLeft + ui::scaled(2, dpi), xOf(current_ + 1));
        rulerHighlightLayer_.blit(dc, currentLeft, r.top, currentRight - currentLeft, tickBottom - r.top,
                                  currentLeft - r.left, 0);
    }

    // 下端の帯: キャッシュに入っているコマ。
    for (const auto& [runLeft, runRight] : cacheRuns_) {
        ui::fill(dc, RECT{runLeft, r.bottom - strip, runRight, r.bottom}, ui::kAccent);
    }

    // 現在のフレームの番号は、区画の右下に箱で出す(右端で入らなければ左側)。
    // 再生範囲の外にいるときは、外れている側の端に矢印付きの箱で出す(どこにいるか見失わないように)。
    HGDIOBJ oldFont = SelectObject(dc, fonts_.get(ui::kSmallPoints, dpi));
    wchar_t text[32];
    if (currentInRange) {
        std::swprintf(text, 32, L"%d", currentSceneFrame());
    } else {
        std::swprintf(text, 32, current_ < first ? L"◀ %d" : L"%d ▶", currentSceneFrame());
    }
    SIZE size{};
    GetTextExtentPoint32W(dc, text, static_cast<int>(wcslen(text)), &size);
    const int boxWidth = size.cx + ui::scaled(8, dpi);
    const int boxHeight = size.cy + ui::scaled(2, dpi);
    int boxLeft = 0;
    if (currentInRange) {
        boxLeft = currentRight + 1;
        if (boxLeft + boxWidth > r.right) {
            boxLeft = currentLeft - 1 - boxWidth;
        }
    } else {
        boxLeft = current_ < first ? static_cast<int>(r.left) : static_cast<int>(r.right) - boxWidth;
    }
    RECT box{boxLeft, tickBottom - boxHeight, boxLeft + boxWidth, tickBottom};
    ui::fill(dc, box, ui::kLabelBox);
    SetTextColor(dc, currentInRange ? ui::kText : ui::kAccent);
    DrawTextW(dc, text, -1, &box, DT_CENTER | DT_VCENTER | DT_SINGLELINE);
    SelectObject(dc, oldFont);
}

int PlayerWindow::rangeXOf(const Layout& layout, int index) const {
    const RECT& b = layout.rangeBar;
    const long long count = std::max(1LL, static_cast<long long>(animLast_) - animFirst_ + 1);
    return static_cast<int>(b.left) +
           static_cast<int>((static_cast<long long>(index) - animFirst_) * (b.right - b.left) / count);
}

void PlayerWindow::paintRangeSlider(HDC dc, const Layout& layout, int dpi) {
    const RECT& b = layout.rangeBar;
    if (b.right - b.left < 2) {
        return;
    }
    ui::fill(dc, b, ui::kRuler);
    if (!clip_) {
        return;
    }
    // 地: 全体範囲のうち動画の外は暗く、動画のある所は普通の地で塗る。
    const int clipLeft = std::clamp(rangeXOf(layout, 0), static_cast<int>(b.left), static_cast<int>(b.right));
    const int clipRight =
        std::clamp(rangeXOf(layout, clip_->frameCount()), static_cast<int>(b.left), static_cast<int>(b.right));
    ui::fill(dc, b, ui::kRulerOutside);
    if (clipRight > clipLeft) {
        ui::fill(dc, RECT{clipLeft, b.top, clipRight, b.bottom}, ui::kRuler);
    }
    // 再生範囲を明るく塗り(動画の外の部分は少し暗く)、両端につまみを置く。範囲の番号は両脇の欄に出す。
    const int x0 = rangeXOf(layout, playFirst_);
    const int x1 = std::max(x0 + ui::scaled(2, dpi), rangeXOf(layout, playLast_ + 1));
    const int handle = ui::scaled(6, dpi);
    ui::fill(dc, RECT{x0, b.top, x1, b.bottom}, ui::kRangeSelectedOutside);
    if (std::min(x1, clipRight) > std::max(x0, clipLeft)) {
        ui::fill(dc, RECT{std::max(x0, clipLeft), b.top, std::min(x1, clipRight), b.bottom}, ui::kRangeSelected);
    }
    ui::fill(dc, RECT{x0, b.top, x0 + handle, b.bottom}, ui::kHandle);
    ui::fill(dc, RECT{std::max(x0, x1 - handle), b.top, x1, b.bottom}, ui::kHandle);

    // 下端の帯: 全体範囲のうちキャッシュに入っているコマ。
    const int strip = ui::scaled(2, dpi);
    for (const auto& [runLeft, runRight] : rangeCacheRuns_) {
        ui::fill(dc, RECT{runLeft, b.bottom - strip, runRight, b.bottom}, ui::kAccent);
    }
}

void PlayerWindow::paintField(HDC dc, const RECT& rect, int value, Part part, bool primary, int dpi) {
    const bool hover = clip_ && hover_ == part;
    ui::fill(dc, rect, hover ? ui::kControlHover : primary ? ui::kControlFace : ui::kSurface);
    ui::frame(dc, rect, hover ? ui::kControlBorderHover : ui::kControlBorder);
    if (!clip_) {
        return;
    }
    HGDIOBJ oldFont = SelectObject(dc, fonts_.get(ui::kTextPoints, dpi));
    SetTextColor(dc, primary ? ui::kText : ui::kSecondaryText);
    wchar_t text[32];
    std::swprintf(text, 32, L"%d", value);
    RECT textRect = rect;
    DrawTextW(dc, text, -1, &textRect, DT_CENTER | DT_VCENTER | DT_SINGLELINE);
    SelectObject(dc, oldFont);
}

void PlayerWindow::paintVolume(HDC dc, const Layout& layout, int dpi) {
    // 比較中は音声を鳴らさないので、音声なしと同じく薄く表示する。
    const bool hasAudio = audio_ && audio_->hasAudio() && !compareClip_;
    // 音声の無い動画のときは、操作はできるが薄い色で描く(設定は次の動画に引き継がれる)。
    const COLORREF ink = (clip_ && !hasAudio) ? ui::kDisabled : ui::kText;

    // スピーカーの形(四角+台形)。消音中は×、そうでなければ音の大きさに応じて弧を描く。
    const RECT& b = layout.volumeButton;
    const int cy = (b.top + b.bottom) / 2;
    const int unit = std::max(1, static_cast<int>((b.bottom - b.top) / 8));
    const int left = b.left + unit;
    const POINT speaker[] = {{left, cy - unit},         {left + 2 * unit, cy - unit}, {left + 4 * unit, cy - 3 * unit},
                             {left + 4 * unit, cy + 3 * unit}, {left + 2 * unit, cy + unit}, {left, cy + unit}};
    HPEN pen = CreatePen(PS_SOLID, std::max(1, ui::scaled(2, dpi) / 2 + 1), ink);
    HGDIOBJ oldBrush = SelectObject(dc, GetStockObject(DC_BRUSH));
    SetDCBrushColor(dc, ink);
    HGDIOBJ oldPen = SelectObject(dc, pen);
    Polygon(dc, speaker, static_cast<int>(std::size(speaker)));
    SelectObject(dc, GetStockObject(NULL_BRUSH));
    const int waveX = left + 5 * unit;
    if (settings_.muted) {
        MoveToEx(dc, waveX, cy - 2 * unit, nullptr);
        LineTo(dc, waveX + 3 * unit, cy + 2 * unit);
        MoveToEx(dc, waveX + 3 * unit, cy - 2 * unit, nullptr);
        LineTo(dc, waveX, cy + 2 * unit);
    } else {
        const int waves = settings_.volume <= 0.0f ? 0 : (settings_.volume < 0.5f ? 1 : 2);
        for (int i = 1; i <= waves; ++i) {
            const int r = (i + 1) * unit + unit / 2;
            Arc(dc, waveX - r, cy - r, waveX + r, cy + r, waveX + r, cy + r, waveX + r, cy - r);
        }
    }
    SelectObject(dc, oldBrush);
    SelectObject(dc, oldPen);
    DeleteObject(pen);

    // 音量は右上がりの三角形で示す(Keyframe Proと同じ)。左から音量の分だけ塗り、残りは枠だけ。
    const RECT& s = layout.volumeSlider;
    const int width = std::max(1L, s.right - s.left);
    const int height = s.bottom - s.top;
    const POINT outline[] = {{s.left, s.bottom}, {s.right, s.bottom}, {s.right, s.top}};
    oldBrush = SelectObject(dc, GetStockObject(DC_BRUSH));
    oldPen = SelectObject(dc, GetStockObject(NULL_PEN));
    SetDCBrushColor(dc, ui::kVolumeTrack);
    Polygon(dc, outline, 3);
    const int fx = s.left + static_cast<int>(width * settings_.volume + 0.5f);
    if (fx > s.left) {
        const POINT filled[] = {{s.left, s.bottom}, {fx, s.bottom}, {fx, s.bottom - height * (fx - s.left) / width}};
        SetDCBrushColor(dc, (settings_.muted || !hasAudio) ? ui::kDisabled : ui::kAccent);
        Polygon(dc, filled, 3);
    }
    SelectObject(dc, oldBrush);
    SelectObject(dc, oldPen);

    // 音量の数字は三角形の左上の空いている所に小さく出す。
    HGDIOBJ oldFont = SelectObject(dc, fonts_.get(ui::kSmallPoints - 1, dpi));
    SetTextColor(dc, ui::kText);
    wchar_t percent[16];
    std::swprintf(percent, 16, settings_.muted ? L"消音" : L"%d%%", static_cast<int>(settings_.volume * 100.0f + 0.5f));
    RECT percentRect{s.left, s.top - ui::scaled(2, dpi), s.left + width * 2 / 3, s.top + height / 2};
    DrawTextW(dc, percent, -1, &percentRect, DT_LEFT | DT_TOP | DT_SINGLELINE | DT_NOCLIP);
    SelectObject(dc, oldFont);
}

void PlayerWindow::onKeyDown(WPARAM key) {
    const bool shift = GetKeyState(VK_SHIFT) < 0;
    // Ctrl+O: 1本目をファイル選択画面で開く。Ctrl+Shift+O: 2本目(比較)を開く。
    if (key == 'O' && GetKeyState(VK_CONTROL) < 0) {
        const std::wstring path = chooseVideoFile(shift ? L"比較する動画を選択" : L"動画を選択");
        if (!path.empty()) {
            if (shift) {
                openCompare(path);
            } else {
                openClip(path);
            }
        }
        return;
    }
    // [ ]: 比較中の2本目のオフセットを1コマ(Shift併用で10コマ)変える。
    if ((key == VK_OEM_4 || key == VK_OEM_6) && compareClip_) {
        const int amount = shift ? kCompareLargeShift : 1;
        shiftCompare(key == VK_OEM_4 ? -amount : amount);
        return;
    }
    // 音量の操作は動画を開いていなくても受け付ける。
    switch (key) {
    case 'M':
        toggleMute();
        return;
    case VK_UP:
        setVolume(settings_.volume + kVolumeStep);
        return;
    case VK_DOWN:
        setVolume(settings_.volume - kVolumeStep);
        return;
    default:
        break;
    }
    if (!clip_) {
        return;
    }
    if (key == VK_SPACE) {
        togglePlayback();
        return;
    }
    const int current = view_.currentFrame();
    switch (key) {
    case VK_RIGHT:
        if (shift) {
            goToFrame(current + kLargeStep);
        } else {
            stepFrame(1);
        }
        break;
    case VK_LEFT:
        if (shift) {
            goToFrame(current - kLargeStep);
        } else {
            stepFrame(-1);
        }
        break;
    case VK_HOME:
        goToFrame(playFirst_);
        break;
    case VK_END:
        goToFrame(playLast_);
        break;
    case 'I':
        // 再生範囲の最初を今のフレームにする(最後より後なら最後も合わせる)。
        setPlaybackRange(current, std::max(playLast_, current));
        break;
    case 'O':
        // 再生範囲の最後を今のフレームにする(最初より前なら最初も合わせる)。
        setPlaybackRange(std::min(playFirst_, current), current);
        break;
    default:
        break;
    }
}

void PlayerWindow::stepFrame(int delta) {
    // Mayaと同じく、再生範囲の端で1コマ送ると反対の端へ回り込む(範囲の外にいるときは回り込まない)。
    const int current = view_.currentFrame();
    int next = current + delta;
    if (current >= playFirst_ && current <= playLast_) {
        if (next > playLast_) {
            next = playFirst_;
        } else if (next < playFirst_) {
            next = playLast_;
        }
    }
    goToFrame(next);
}

void PlayerWindow::onLeftButtonDown(int x, int y) {
    if (editField_ != EditField::None) {
        commitEdit();  // 入力中に他の所を押したら、入力を確定する。
    }
    const Layout layout = computeLayout();
    const int dpi = static_cast<int>(GetDpiForWindow(hwnd_));
    const POINT point{x, y};
    // 音量の三角形は小さいので、レンジスライダーの段の高さいっぱいまで当たり判定を広げる。
    RECT volumeHit = layout.volumeSlider;
    volumeHit.top = layout.rangeRow.top;
    volumeHit.bottom = layout.rangeRow.bottom;
    InflateRect(&volumeHit, ui::scaled(4, dpi), 0);
    if (PtInRect(&layout.fileButton, point)) {
        showFileMenu();
        return;
    }
    if (PtInRect(&layout.volumeButton, point)) {
        toggleMute();
        return;
    }
    if (PtInRect(&layout.syncButton, point)) {
        setSyncEnabled(!syncEnabled());
        return;
    }
    if (PtInRect(&layout.compareButton, point)) {
        if (compareClip_) {
            closeCompare();
        } else {
            const std::wstring path = chooseVideoFile(L"比較する動画を選択");
            if (!path.empty()) {
                openCompare(path);
            }
        }
        return;
    }
    if (PtInRect(&volumeHit, point)) {
        drag_ = Drag::Volume;
        SetCapture(hwnd_);
        setVolume(volumeFromX(x));
        return;
    }
    if (!clip_) {
        return;
    }
    if (PtInRect(&layout.currentField, point)) {
        beginEdit(EditField::Current);
        return;
    }
    const std::pair<const RECT*, EditField> fields[] = {
        {&layout.animStartField, EditField::AnimStart}, {&layout.playStartField, EditField::PlayStart},
        {&layout.playEndField, EditField::PlayEnd},     {&layout.animEndField, EditField::AnimEnd},
        {&layout.clipStartField, EditField::ClipStart},
    };
    for (const auto& [rect, field] : fields) {
        if (PtInRect(rect, point)) {
            beginEdit(field);
            return;
        }
    }
    if (PtInRect(&layout.button, point)) {
        togglePlayback();
        return;
    }
    if (PtInRect(&layout.startButton, point)) {
        goToFrame(playFirst_);
        return;
    }
    if (PtInRect(&layout.prevButton, point)) {
        stepFrame(-1);
        return;
    }
    if (PtInRect(&layout.nextButton, point)) {
        stepFrame(1);
        return;
    }
    if (PtInRect(&layout.endButton, point)) {
        goToFrame(playLast_);
        return;
    }
    RECT rulerHit = layout.ruler;
    rulerHit.top = layout.timeRow.top;
    rulerHit.bottom = layout.timeRow.bottom;
    if (PtInRect(&rulerHit, point)) {
        // 目盛りの段のどこを押してもよい。ドラッグ中にウィンドウ外へ出てもマウスの動きを受け取れるよう、
        // マウスを取り込む。再生中に触った場合は、ドラッグ中はそのコマを表示し、離したらその位置から再生を続ける。
        resumeAfterScrub_ = view_.isPlaying();
        drag_ = Drag::Scrub;
        SetCapture(hwnd_);
        goToFrame(frameFromX(x), true);
        return;
    }
    RECT rangeHit = layout.rangeBar;
    rangeHit.top = layout.rangeRow.top;
    rangeHit.bottom = layout.rangeRow.bottom;
    if (PtInRect(&rangeHit, point)) {
        // つまみなら範囲の端を、範囲の中なら長さを保って範囲を動かす。
        drag_ = hitTestRange(layout, x);
        if (drag_ == Drag::None) {
            return;
        }
        dragAnchor_ = rangeFrameFromX(x);
        dragFirst_ = playFirst_;
        dragLast_ = playLast_;
        SetCapture(hwnd_);
    }
}

void PlayerWindow::onMiddleButtonDown(int x, int y) {
    if (!clip_ || drag_ != Drag::None) {
        return;
    }
    const Layout layout = computeLayout();
    const POINT point{x, y};
    if (!PtInRect(&layout.video, point)) {
        return;
    }
    if (editField_ != EditField::None) {
        commitEdit();
    }
    // 比較中は左右の半分ずつがそれぞれの動画の表示枠(VideoViewと同じ分け方)。
    const bool comparePane = compareClip_ && x >= (layout.video.left + layout.video.right) / 2;
    drag_ = comparePane ? Drag::PaneCompare : Drag::PaneMain;
    // 左右どちらでも、タイムスライダーのドラッグと同じく押した時点で再生を止め、離したら再生を続ける
    // (動かしている間は、合わせたいコマを止まった状態で見比べられるように)。
    resumeAfterScrub_ = view_.isPlaying();
    if (resumeAfterScrub_) {
        togglePlayback();
    }
    paneDragX_ = x;
    paneDragFrame_ = view_.currentFrame();
    paneDragOffset_ = view_.compareOffset();
    // ウィンドウの外へ出てもマウスの動きを受け取れるよう取り込む(取り込み中はWM_SETCURSORが来ないので、ここで形を決める)。
    SetCapture(hwnd_);
    SetCursor(LoadCursorW(nullptr, IDC_SIZEWE));
}

void PlayerWindow::onMouseMove(int x, int y) {
    if (drag_ == Drag::None) {
        // マウスが乗っている部品を明るくする。ウィンドウから出たときに戻せるよう、出たことの知らせを頼んでおく。
        if (!trackingLeave_) {
            TRACKMOUSEEVENT track{sizeof(TRACKMOUSEEVENT), TME_LEAVE, hwnd_, 0};
            trackingLeave_ = TrackMouseEvent(&track) != FALSE;
        }
        setHover(hitTestPart(computeLayout(), POINT{x, y}));
        return;
    }
    switch (drag_) {
    case Drag::PaneMain:
    case Drag::PaneCompare:
        if (clip_) {
            // 押した位置からの距離をコマ数にする(0の前後で幅が変わらないよう、負の側も同じ幅で区切る)。
            const int perFrame =
                std::max(1, ui::scaled(kPaneDragPixelsPerFrame, static_cast<int>(GetDpiForWindow(hwnd_))));
            const int moved = x - paneDragX_;
            const int frames = moved >= 0 ? moved / perFrame : -((-moved + perFrame - 1) / perFrame);
            if (drag_ == Drag::PaneCompare) {
                if (compareClip_ && paneDragOffset_ + frames != view_.compareOffset()) {
                    shiftCompare(paneDragOffset_ + frames - view_.compareOffset());
                }
            } else {
                // 1本目だけを動かす: 動かした分だけオフセットを逆に変え、2本目に表示するコマはそのままにする。
                const int target = clampIndex(static_cast<long long>(paneDragFrame_) + frames);
                std::optional<int> offset;
                if (compareClip_) {
                    offset = paneDragOffset_ - (target - paneDragFrame_);
                }
                goToFrame(target, true, offset);
            }
        }
        break;
    case Drag::Volume:
        setVolume(volumeFromX(x));
        break;
    case Drag::Scrub:
        if (clip_) {
            goToFrame(frameFromX(x), true);
        }
        break;
    case Drag::RangeStart:
        if (clip_) {
            setPlaybackRange(std::min(rangeFrameFromX(x), playLast_), playLast_);
        }
        break;
    case Drag::RangeEnd:
        if (clip_) {
            setPlaybackRange(playFirst_, std::max(rangeFrameFromX(x), playFirst_));
        }
        break;
    case Drag::RangeMove:
        if (clip_) {
            // 長さを保ったまま、全体範囲からはみ出さないように動かす。
            const int length = dragLast_ - dragFirst_;
            const int first = std::clamp(dragFirst_ + rangeFrameFromX(x) - dragAnchor_, animFirst_,
                                         std::max(animFirst_, animLast_ - length));
            setPlaybackRange(first, first + length);
        }
        break;
    case Drag::None:
        break;
    }
}

RECT PlayerWindow::partRect(const Layout& layout, Part part) const {
    const int dpi = static_cast<int>(GetDpiForWindow(hwnd_));
    switch (part) {
    case Part::Ruler:
        return RECT{layout.ruler.left, layout.timeRow.top, layout.ruler.right, layout.timeRow.bottom};
    case Part::CurrentField:
        return layout.currentField;
    case Part::StartButton:
        return layout.startButton;
    case Part::PrevButton:
        return layout.prevButton;
    case Part::PlayButton:
        return layout.button;
    case Part::NextButton:
        return layout.nextButton;
    case Part::EndButton:
        return layout.endButton;
    case Part::AnimStartField:
        return layout.animStartField;
    case Part::PlayStartField:
        return layout.playStartField;
    case Part::RangeBar:
        return RECT{layout.rangeBar.left, layout.rangeRow.top, layout.rangeBar.right, layout.rangeRow.bottom};
    case Part::PlayEndField:
        return layout.playEndField;
    case Part::AnimEndField:
        return layout.animEndField;
    case Part::ClipStartField:
        return layout.clipStartField;
    case Part::SyncButton:
        return layout.syncButton;
    case Part::FileButton:
        return layout.fileButton;
    case Part::CompareButton:
        return layout.compareButton;
    case Part::VolumeButton:
        return layout.volumeButton;
    case Part::VolumeSlider: {
        // 音量の三角形は小さいので、レンジスライダーの段の高さいっぱいまで広げる。
        RECT hit{layout.volumeSlider.left, layout.rangeRow.top, layout.volumeSlider.right, layout.rangeRow.bottom};
        InflateRect(&hit, ui::scaled(4, dpi), 0);
        return hit;
    }
    default:
        return RECT{};
    }
}

PlayerWindow::Part PlayerWindow::hitTestPart(const Layout& layout, POINT point) const {
    for (UINT_PTR i = 1; i < static_cast<UINT_PTR>(Part::Count); ++i) {
        const RECT r = partRect(layout, static_cast<Part>(i));
        if (PtInRect(&r, point)) {
            return static_cast<Part>(i);
        }
    }
    return Part::None;
}

const wchar_t* PlayerWindow::tooltipText(Part part) const {
    switch (part) {
    case Part::Ruler:
        return L"タイムスライダー(クリック・ドラッグでフレームを移動)";
    case Part::CurrentField:
        return L"現在のフレーム(押して番号を入力)";
    case Part::StartButton:
        return L"再生範囲の最初へ (Home)";
    case Part::PrevButton:
        return L"1フレーム戻る (← / Alt+,)";
    case Part::PlayButton:
        return L"再生 / 停止 (Space)";
    case Part::NextButton:
        return L"1フレーム進む (→ / Alt+.)";
    case Part::EndButton:
        return L"再生範囲の最後へ (End)";
    case Part::AnimStartField:
        return L"全体範囲の最初";
    case Part::PlayStartField:
        return L"再生範囲の最初 (I で今のフレームにする)";
    case Part::RangeBar:
        return L"再生範囲(つまみで端を、中をドラッグで範囲を動かす。ダブルクリックで全体範囲と切り替え)";
    case Part::PlayEndField:
        return L"再生範囲の最後 (O で今のフレームにする)";
    case Part::AnimEndField:
        return L"全体範囲の最後";
    case Part::ClipStartField:
        return L"動画の開始(動画の1コマ目を置くフレーム番号)";
    case Part::SyncButton:
        if (!syncServer_) {
            return L"Mayaと連携する(押すと連携モード)";
        }
        return syncServer_->connected() ? L"Mayaと連携中(押すと連携を終える)"
                                        : L"Mayaからの接続を待っています(押すと連携を終える)";
    case Part::FileButton:
        return L"動画を開く・最近使ったファイル (Ctrl+O)";
    case Part::CompareButton:
        return compareClip_ ? L"比較を終える" : L"2本目の動画を開いて並べて比べる (Ctrl+Shift+O)";
    case Part::VolumeButton:
        return L"消音の切り替え (M)";
    case Part::VolumeSlider:
        return L"音量 (↑ / ↓)";
    default:
        return L"";
    }
}

void PlayerWindow::createTooltips() {
    // 操作部の部品は子ウィンドウではなく描いているだけなので、部品ごとの範囲をツールチップに登録する。
    // TTF_SUBCLASSで、ツールチップがこのウィンドウのマウスの動きを自分で見て、出す・消すを決める。
    tooltip_ = CreateWindowExW(WS_EX_TOPMOST, TOOLTIPS_CLASSW, nullptr, WS_POPUP | TTS_NOPREFIX | TTS_ALWAYSTIP,
                               CW_USEDEFAULT, CW_USEDEFAULT, CW_USEDEFAULT, CW_USEDEFAULT, hwnd_, nullptr, instance_,
                               nullptr);
    if (!tooltip_) {
        return;
    }
    SetWindowTheme(tooltip_, L"DarkMode_Explorer", nullptr);  // 操作部と同じダークの見た目にする(Windows 10 1809以降)。
    SendMessageW(tooltip_, TTM_SETMAXTIPWIDTH, 0, ui::scaled(360, static_cast<int>(GetDpiForWindow(hwnd_))));
    const Layout layout = computeLayout();
    for (UINT_PTR i = 1; i < static_cast<UINT_PTR>(Part::Count); ++i) {
        TTTOOLINFOW tool{};
        tool.cbSize = sizeof(tool);
        tool.uFlags = TTF_SUBCLASS;
        tool.hwnd = hwnd_;
        tool.uId = i;
        tool.rect = partRect(layout, static_cast<Part>(i));
        tool.lpszText = LPSTR_TEXTCALLBACKW;  // 文字はWM_NOTIFY(TTN_GETDISPINFO)で、その時の状態に合わせて返す。
        SendMessageW(tooltip_, TTM_ADDTOOLW, 0, reinterpret_cast<LPARAM>(&tool));
    }
}

void PlayerWindow::updateTooltipRects() {
    if (!tooltip_) {
        return;
    }
    const Layout layout = computeLayout();
    for (UINT_PTR i = 1; i < static_cast<UINT_PTR>(Part::Count); ++i) {
        TTTOOLINFOW tool{};
        tool.cbSize = sizeof(tool);
        tool.hwnd = hwnd_;
        tool.uId = i;
        tool.rect = partRect(layout, static_cast<Part>(i));
        SendMessageW(tooltip_, TTM_NEWTOOLRECTW, 0, reinterpret_cast<LPARAM>(&tool));
    }
}

void PlayerWindow::setHover(Part part) {
    // 明るく表示するのは押せる部品だけ(目盛りとバーはドラッグで操作するので、明るくしない)。
    if (part == Part::Ruler || part == Part::RangeBar || part == Part::VolumeSlider) {
        part = Part::None;
    }
    if (part == hover_) {
        return;
    }
    hover_ = part;
    invalidateBar();
}

void PlayerWindow::onDoubleClick(int x, int y) {
    const Layout layout = computeLayout();
    const POINT point{x, y};
    RECT rangeHit = layout.rangeBar;
    rangeHit.top = layout.rangeRow.top;
    rangeHit.bottom = layout.rangeRow.bottom;
    if (clip_ && PtInRect(&rangeHit, point)) {
        // Mayaと同じく、全体範囲と、直前の再生範囲を切り替える。
        if (playFirst_ == animFirst_ && playLast_ == animLast_) {
            if (hasSavedRange_ && savedFirst_ >= animFirst_ && savedLast_ >= savedFirst_ && savedLast_ <= animLast_) {
                setPlaybackRange(savedFirst_, savedLast_);
            }
        } else {
            savedFirst_ = playFirst_;
            savedLast_ = playLast_;
            hasSavedRange_ = true;
            setPlaybackRange(animFirst_, animLast_);
        }
        return;
    }
    // ダブルクリックの2回目も、普通のクリックとして扱う(ボタンの連打で取りこぼさないように)。
    onLeftButtonDown(x, y);
}

bool PlayerWindow::updateCursor() {
    if (!clip_) {
        return false;
    }
    Drag target = drag_;
    if (target == Drag::None) {
        POINT point;
        GetCursorPos(&point);
        ScreenToClient(hwnd_, &point);
        const Layout layout = computeLayout();
        if (point.y >= layout.rangeBar.top && point.y < layout.rangeBar.bottom) {
            target = hitTestRange(layout, point.x);
        }
    }
    const bool sizing = target == Drag::RangeStart || target == Drag::RangeEnd || target == Drag::PaneMain ||
                        target == Drag::PaneCompare;
    if (sizing) {
        SetCursor(LoadCursorW(nullptr, IDC_SIZEWE));
    }
    return sizing;
}

void PlayerWindow::endScrub() {
    const bool resume = resumeAfterScrub_;
    if ((drag_ == Drag::Scrub || drag_ == Drag::PaneMain) && clip_) {
        updateTitle();  // ドラッグ中は間引いていたので、離した位置にする。
    }
    if (drag_ != Drag::None) {
        // ReleaseCapture()はWM_CAPTURECHANGEDをすぐ送ってくるので、先に状態を戻しておく。
        drag_ = Drag::None;
        resumeAfterScrub_ = false;
        ReleaseCapture();
    }
    if (resume) {
        resumePlayback();
    }
}

void PlayerWindow::setVolume(float volume) {
    settings_.volume = std::clamp(volume, 0.0f, 1.0f);
    settings_.muted = false;  // 音量を変えたら消音は解除する(一般的なプレイヤーと同じ)。
    if (audio_) {
        audio_->setVolume(settings_.volume);
        audio_->setMuted(false);
    }
    settings_.saveAudio();
    invalidateBar();
}

void PlayerWindow::toggleMute() {
    settings_.muted = !settings_.muted;
    if (audio_) {
        audio_->setMuted(settings_.muted);
    }
    settings_.saveAudio();
    invalidateBar();
}

float PlayerWindow::volumeFromX(int x) const {
    const RECT s = computeLayout().volumeSlider;
    const int width = std::max(1L, s.right - s.left);
    return std::clamp(static_cast<float>(x - s.left) / width, 0.0f, 1.0f);
}

PlayerWindow::Drag PlayerWindow::hitTestRange(const Layout& layout, int x) const {
    // つまみは見た目(6ピクセル)より少し広めに判定する。範囲がとても狭く両方のつまみにかかるときは、近い方。
    const int dpi = static_cast<int>(GetDpiForWindow(hwnd_));
    const int x0 = rangeXOf(layout, playFirst_);
    const int x1 = std::max(x0 + ui::scaled(2, dpi), rangeXOf(layout, playLast_ + 1));
    const int handle = ui::scaled(9, dpi);
    const int slack = ui::scaled(3, dpi);
    if (x >= x0 - slack && x < x0 + handle && (x - x0) <= (x1 - x)) {
        return Drag::RangeStart;
    }
    if (x <= x1 + slack && x > x1 - handle) {
        return Drag::RangeEnd;
    }
    if (x >= x0 && x < x1) {
        return Drag::RangeMove;
    }
    return Drag::None;
}

int PlayerWindow::frameFromX(int x) const {
    const RECT ruler = computeLayout().ruler;
    const int width = ruler.right - ruler.left;
    const int count = playLast_ - playFirst_ + 1;
    if (count <= 1 || width <= 0) {
        return playFirst_;
    }
    // 目盛りの区画(コマごとに同じ幅)のうち、xを含む区画のコマ。
    const long long offset = static_cast<long long>(x - ruler.left) * count / width;
    return std::clamp(playFirst_ + static_cast<int>(offset), playFirst_, playLast_);
}

int PlayerWindow::rangeFrameFromX(int x) const {
    const RECT bar = computeLayout().rangeBar;
    const int width = bar.right - bar.left;
    const long long count = static_cast<long long>(animLast_) - animFirst_ + 1;
    if (count <= 1 || width <= 0) {
        return animFirst_;
    }
    const long long offset = static_cast<long long>(x - bar.left) * count / width;
    return static_cast<int>(std::clamp(animFirst_ + offset, static_cast<long long>(animFirst_),
                                       static_cast<long long>(animLast_)));
}

void PlayerWindow::beginEdit(EditField field) {
    if (!clip_) {
        return;
    }
    if (editField_ != EditField::None) {
        commitEdit();
    }
    const Layout layout = computeLayout();
    const int dpi = static_cast<int>(GetDpiForWindow(hwnd_));
    const int start = settings_.startFrame;
    RECT r = layout.currentField;
    int value = currentSceneFrame();
    switch (field) {
    case EditField::AnimStart:
        r = layout.animStartField;
        value = start + animFirst_;
        break;
    case EditField::PlayStart:
        r = layout.playStartField;
        value = start + playFirst_;
        break;
    case EditField::PlayEnd:
        r = layout.playEndField;
        value = start + playLast_;
        break;
    case EditField::AnimEnd:
        r = layout.animEndField;
        value = start + animLast_;
        break;
    case EditField::ClipStart:
        r = layout.clipStartField;
        value = start;
        break;
    default:
        break;
    }
    // 欄の上に、同じ大きさの入力用の子ウィンドウを重ねる。文字の高さに合わせて上下の中央に置く。
    HFONT font = fonts_.get(9, dpi);
    const int textHeight = ui::scaled(16, dpi);
    const int top = r.top + (r.bottom - r.top - textHeight) / 2;
    editField_ = field;
    editControl_ = CreateWindowExW(0, L"EDIT", std::to_wstring(value).c_str(),
                                   WS_CHILD | WS_VISIBLE | ES_CENTER | ES_AUTOHSCROLL, r.left + 2, top,
                                   r.right - r.left - 4, textHeight, hwnd_, nullptr, instance_, nullptr);
    if (!editControl_) {
        editField_ = EditField::None;
        return;
    }
    SendMessageW(editControl_, WM_SETFONT, reinterpret_cast<WPARAM>(font), FALSE);
    // EnterとEscを受け取るため、入力用の子ウィンドウのメッセージを横取りする(Windows標準のサブクラス化)。
    SetWindowSubclass(editControl_, &PlayerWindow::editProc, 1, reinterpret_cast<DWORD_PTR>(this));
    SendMessageW(editControl_, EM_SETSEL, 0, -1);
    SetFocus(editControl_);
}

void PlayerWindow::commitEdit() {
    if (editField_ == EditField::None || !editControl_) {
        return;
    }
    wchar_t text[64] = {};
    GetWindowTextW(editControl_, text, 64);
    const EditField field = editField_;
    // 先に状態を戻してから子ウィンドウを壊す(壊すときの「入力欄から離れた」知らせで、もう一度確定しないように)。
    editField_ = EditField::None;
    HWND edit = editControl_;
    editControl_ = nullptr;
    SetFocus(hwnd_);
    DestroyWindow(edit);

    wchar_t* end = nullptr;
    const long value = std::wcstol(text, &end, 10);
    while (end && *end == L' ') {
        ++end;
    }
    if (end == text || (end && *end != L'\0')) {
        invalidateBar();
        return;  // 数字として読めない。
    }
    // 入力はフレーム番号。範囲の欄はMayaと同じく、矛盾する側の値を押して合わせる
    // (例: 全体範囲の最初を再生範囲の最初より後にしたら、再生範囲の最初も同じにする)。
    const int scene = static_cast<int>(std::clamp<long long>(value, -kMaxSyncFrame, kMaxSyncFrame));
    const int index = clampIndex(static_cast<long long>(scene) - settings_.startFrame);
    switch (field) {
    case EditField::Current:
        goToSceneFrame(scene);
        break;
    case EditField::AnimStart:
        setTimeRange(index, std::max(animLast_, index), std::max(playFirst_, index), std::max(playLast_, index));
        break;
    case EditField::AnimEnd:
        setTimeRange(std::min(animFirst_, index), index, std::min(playFirst_, index), std::min(playLast_, index));
        break;
    case EditField::PlayStart:
        setPlaybackRange(index, std::max(playLast_, index));
        break;
    case EditField::PlayEnd:
        setPlaybackRange(std::min(playFirst_, index), index);
        break;
    case EditField::ClipStart:
        setClipStart(scene);
        break;
    default:
        break;
    }
    InvalidateRect(hwnd_, nullptr, FALSE);
}

void PlayerWindow::cancelEdit() {
    if (editField_ == EditField::None || !editControl_) {
        return;
    }
    editField_ = EditField::None;
    HWND edit = editControl_;
    editControl_ = nullptr;
    SetFocus(hwnd_);
    DestroyWindow(edit);
    invalidateBar();
}

LRESULT CALLBACK PlayerWindow::editProc(HWND hwnd, UINT message, WPARAM wParam, LPARAM lParam, UINT_PTR id,
                                        DWORD_PTR data) {
    auto* self = reinterpret_cast<PlayerWindow*>(data);
    switch (message) {
    case WM_KEYDOWN:
        // EnterとEscは、子ウィンドウの処理中に自分を壊さないよう、親へPostMessageで知らせて後で処理する。
        if (wParam == VK_RETURN) {
            PostMessageW(self->hwnd_, kEditCommitMessage, 0, 0);
            return 0;
        }
        if (wParam == VK_ESCAPE) {
            PostMessageW(self->hwnd_, kEditCancelMessage, 0, 0);
            return 0;
        }
        break;
    case WM_CHAR:
        if (wParam == L'\r' || wParam == 0x1B) {
            return 0;  // 1行の入力欄にEnter・Escを渡すと警告音が鳴るので渡さない。
        }
        break;
    case WM_NCDESTROY:
        RemoveWindowSubclass(hwnd, &PlayerWindow::editProc, id);
        break;
    default:
        break;
    }
    return DefSubclassProc(hwnd, message, wParam, lParam);
}

}  // namespace frameplayer
