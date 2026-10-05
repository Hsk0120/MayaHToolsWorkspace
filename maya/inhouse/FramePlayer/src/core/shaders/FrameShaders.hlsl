// FramePlayerの映像のシェーダー(Direct3D 11、シェーダーモデル4.0)。
// ビルド時にfxcで入口ごとにバイトコードの.hへ変換し、FrameRendererが使う。
//   VSFullscreen : 表示先いっぱいの三角形(頂点バッファーなし)
//   PSDownscale  : YUVの1つの面を縮小する(デコード直後。キャッシュを小さくする)
//   PSConvert    : YUVをRGBへ戻す(色の解釈の行列・範囲・色の位置に従う)
//   PSPresent    : 拡大縮小して、色域・明るさを画面に合わせて出す
// 式はITU-R BT.601/709/2020/2100・BT.2390、IEC 61966-2-1から書いた。

struct VSOut {
    float4 pos : SV_Position;
    float2 uv : TEXCOORD0;
};

// 頂点番号0,1,2から、表示先を覆う大きな三角形を作る。
VSOut VSFullscreen(uint id : SV_VertexID) {
    float2 uv = float2((id << 1) & 2, id & 2);
    VSOut o;
    o.pos = float4(uv * float2(2, -2) + float2(-1, 1), 0, 1);
    o.uv = uv;
    return o;
}

SamplerState gLinear : register(s0);  // 線形補間・端は延長。

// ---------------------------------------------------------------- 縮小
Texture2D<float4> gDownscaleSource : register(t0);

cbuffer DownscaleParams : register(b0) {
    float2 gScale;       // 元の画素数 / 先の画素数
    float2 gBias;        // 色の面の位置合わせ(明るさの面は0)
    float2 gSourceSize;  // 元の面の大きさ(画素)
    int2 gTaps;          // 縦横に足し合わせる数
};

// 先の1画素が覆う元の範囲を、等間隔の線形補間の平均で求める(面積の平均に近い縮小)。
float4 PSDownscale(VSOut input) : SV_Target {
    float2 center = input.pos.xy * gScale + gBias;
    float4 sum = 0;
    [loop] for (int j = 0; j < gTaps.y; ++j) {
        [loop] for (int i = 0; i < gTaps.x; ++i) {
            float2 offset = (float2(i + 0.5, j + 0.5) / float2(gTaps) - 0.5) * gScale;
            sum += gDownscaleSource.SampleLevel(gLinear, (center + offset) / gSourceSize, 0);
        }
    }
    return sum / (gTaps.x * gTaps.y);
}

// ---------------------------------------------------------------- YUV → RGB
Texture2D<float4> gPlane0 : register(t0);  // 明るさの面(RGBのコマならRGB)
Texture2D<float4> gPlane1 : register(t1);  // 色の面(UVの交互)

cbuffer ConvertParams : register(b0) {
    float4 gRow0;          // RGB = 行列 × (Y, Cb, Cr, 1)
    float4 gRow1;
    float4 gRow2;
    float2 gChromaOffset;  // 色の画素の位置(明るさの画素の単位。左寄せなら(0, 0.5))
    float2 gChromaSize;    // 色の面の大きさ(画素)
    int gIsRgb;            // 0=NV12・P010、1=RGBのコマ(そのまま写す)、2=YUY2(1テクセルに「Y0 U Y1 V」)
    int3 gPad0;
};

float4 PSConvert(VSOut input) : SV_Target {
    int2 p = int2(input.pos.xy);
    if (gIsRgb == 1) {
        return float4(saturate(gPlane0.Load(int3(p, 0)).rgb), 1);
    }
    if (gIsRgb == 2) {
        // YUY2(4:2:2): 横2画素で色を1組持つ。色の画素iは明るさの単位で2i+offsetの位置にあるので、
        // 左右の組を線形に補間する(縦は間引かれていない)。
        float4 pair = gPlane0.Load(int3(p.x >> 1, p.y, 0));
        float luma = (p.x & 1) != 0 ? pair.b : pair.r;
        float position = (p.x - gChromaOffset.x) * 0.5;
        int left = (int)floor(position);
        float t = position - left;
        int last = (int)gChromaSize.x - 1;
        float2 a = gPlane0.Load(int3(clamp(left, 0, last), p.y, 0)).ga;
        float2 b = gPlane0.Load(int3(clamp(left + 1, 0, last), p.y, 0)).ga;
        float4 packedYuv = float4(luma, lerp(a, b, t), 1);
        return float4(saturate(float3(dot(gRow0, packedYuv), dot(gRow1, packedYuv), dot(gRow2, packedYuv))), 1);
    }
    float y = gPlane0.Load(int3(p, 0)).r;
    // 明るさの画素n(中心はn+0.5)に対応する色の面の位置。色の画素iは明るさの単位で2i+offsetにある。
    float2 chroma = (input.pos.xy - 0.5 - gChromaOffset) * 0.5 + 0.5;
    float2 uv = gPlane1.SampleLevel(gLinear, chroma / gChromaSize, 0).rg;
    float4 yuv = float4(y, uv, 1);
    float3 rgb = float3(dot(gRow0, yuv), dot(gRow1, yuv), dot(gRow2, yuv));
    return float4(saturate(rgb), 1);  // 範囲外(映像用の範囲の外側)は画面に出せないので切る。
}

// ---------------------------------------------------------------- 表示
Texture2D<float4> gImage : register(t0);  // PSConvertの結果(縮小用のミップマップ付き)

cbuffer PresentParams : register(b0) {
    float4 gGamut0;       // 色域の変換(リニアな値に掛ける3x3。wは未使用)
    float4 gGamut1;
    float4 gGamut2;
    float2 gImageSize;    // 画像の大きさ(画素)
    float2 gDestOrigin;   // 表示先の左上(描画先の画素座標)
    float2 gStep;         // 表示先の1画素が画像の何画素か
    float gLod;           // 縮小するときに読むミップマップの段
    int gUpscale;         // 1なら拡大(または等倍)。双三次補間で読む
    int gTransfer;        // 0=SDR、1=リニア、2=PQ、3=HLG
    int gOutput;          // 0=値をそのまま8bitへ、1=scRGB(リニア)、2=sRGBにして8bitへ
    float gSdrScale;      // SDRの白(1.0)をscRGBでいくつにするか
    float gHdrScale;      // HDRの画面なら1/80(明るさをscRGBへ)。SDRの画面なら0(明るさを収める)
    float gSourcePeakPq;  // HDRの最大の明るさのPQの値
    float gMaxLum;        // 収める先の最大(基準の白)のPQの値 ÷ gSourcePeakPq
    float gKneeStart;     // 収め始める位置(BT.2390のKS)
    float gReferenceWhite;  // 基準の白の明るさ(cd/m²)
};

static const float PQ_M1 = 2610.0 / 16384.0;
static const float PQ_M2 = 2523.0 / 4096.0 * 128.0;
static const float PQ_C1 = 3424.0 / 4096.0;
static const float PQ_C2 = 2413.0 / 4096.0 * 32.0;
static const float PQ_C3 = 2392.0 / 4096.0 * 32.0;

float3 srgbToLinear(float3 v) {
    return v <= 0.04045 ? v / 12.92 : pow(abs((v + 0.055) / 1.055), 2.4);
}

float3 linearToSrgb(float3 v) {
    return v <= 0.0031308 ? v * 12.92 : 1.055 * pow(abs(v), 1.0 / 2.4) - 0.055;
}

// PQの信号(0〜1)を明るさ(cd/m²)にする。
float3 pqToNits(float3 v) {
    float3 e = pow(saturate(v), 1.0 / PQ_M2);
    return 10000.0 * pow(max(e - PQ_C1, 0) / (PQ_C2 - PQ_C3 * e), 1.0 / PQ_M1);
}

// 明るさ(cd/m²)をPQの信号にする。
float nitsToPq(float nits) {
    float y = pow(max(nits, 0) / 10000.0, PQ_M1);
    return pow((PQ_C1 + PQ_C2 * y) / (1 + PQ_C3 * y), PQ_M2);
}

// HLGの信号を、表示の明るさ(公称のピーク1000cd/m²、γ=1.2)にする。
float3 hlgToNits(float3 v) {
    const float a = 0.17883277;
    const float b = 1 - 4 * a;
    const float c = 0.5 - a * log(4 * a);
    v = saturate(v);
    float3 scene = v <= 0.5 ? v * v / 3.0 : (exp((v - c) / a) + b) / 12.0;
    float ys = dot(scene, float3(0.2627, 0.6780, 0.0593));
    return 1000.0 * (ys > 0 ? pow(ys, 0.2) : 0) * scene;
}

// BT.2390のEETF: 明るさ(cd/m²)を、基準の白までに収める。最も明るい成分に掛けて色合いを保つ。
float3 toneMap(float3 nits) {
    float peak = max(max(nits.r, nits.g), nits.b);
    if (peak <= 0 || gKneeStart >= 1) {
        return nits;
    }
    float e1 = min(nitsToPq(peak) / gSourcePeakPq, 1.0);
    float e2 = e1;
    if (e1 >= gKneeStart) {
        float t = (e1 - gKneeStart) / (1 - gKneeStart);
        float t2 = t * t;
        float t3 = t2 * t;
        e2 = (2 * t3 - 3 * t2 + 1) * gKneeStart + (t3 - 2 * t2 + t) * (1 - gKneeStart) + (-2 * t3 + 3 * t2) * gMaxLum;
    }
    float mapped = pqToNits(e2 * gSourcePeakPq).r;
    return nits * (mapped / peak);
}

float3 gamut(float3 v) {
    return float3(dot(gGamut0.xyz, v), dot(gGamut1.xyz, v), dot(gGamut2.xyz, v));
}

// 8bitへ丸める。ちょうど8bitの値はそのまま(ディザの振れ幅は0.5段未満)、間の値は位置ごとに散らす。
float3 quantize8(float3 v, float2 position) {
    float noise = frac(52.9829189 * frac(dot(position, float2(0.06711056, 0.00583715))));
    return floor(saturate(v) * 255.0 + 0.5 + (noise - 0.5) * 0.98) / 255.0;
}

// Catmull-Romの双三次補間(等倍なら元の値そのまま)。
float3 sampleCubic(float2 source) {
    float2 t = source - 0.5;
    float2 base = floor(t);
    float2 f = t - base;
    float2 w0 = f * (-0.5 + f * (1.0 - 0.5 * f));
    float2 w1 = 1.0 + f * f * (-2.5 + 1.5 * f);
    float2 w2 = f * (0.5 + f * (2.0 - 1.5 * f));
    float2 w3 = f * f * (-0.5 + 0.5 * f);
    float2 weights[4] = {w0, w1, w2, w3};
    int2 maximum = int2(gImageSize) - 1;
    float3 sum = 0;
    [unroll] for (int j = 0; j < 4; ++j) {
        [unroll] for (int i = 0; i < 4; ++i) {
            int2 p = clamp(int2(base) + int2(i - 1, j - 1), int2(0, 0), maximum);
            sum += gImage.Load(int3(p, 0)).rgb * (weights[i].x * weights[j].y);
        }
    }
    return saturate(sum);
}

float4 PSPresent(VSOut input) : SV_Target {
    float2 source = (input.pos.xy - gDestOrigin) * gStep;
    float3 v = gUpscale != 0 ? sampleCubic(source) : gImage.SampleLevel(gLinear, source / gImageSize, gLod).rgb;
    if (gOutput == 0) {
        return float4(quantize8(v, input.pos.xy), 1);  // SDR・BT.709: 値をそのまま出す。
    }
    float3 light;
    if (gTransfer >= 2) {
        float3 nits = gTransfer == 2 ? pqToNits(v) : hlgToNits(v);
        if (gHdrScale > 0) {
            return float4(gamut(nits) * gHdrScale, 1);  // HDRの画面: 明るさそのまま。
        }
        light = gamut(toneMap(nits) / gReferenceWhite);  // SDRの画面: 基準の白を1.0として収める。
    } else {
        light = gamut(gTransfer == 1 ? v : srgbToLinear(v));
    }
    if (gOutput == 1) {
        return float4(light * gSdrScale, 1);
    }
    return float4(quantize8(linearToSrgb(saturate(light)), input.pos.xy), 1);
}
