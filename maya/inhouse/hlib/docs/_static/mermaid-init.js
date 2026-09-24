(function () {
    // SVGにwidth/height指定が無いと、ブラウザはコンテナ幅に縮小して描画する
    // (viewBoxの実サイズは使われない)。図が読めなくなるため、レンダリング後に
    // viewBoxの実ピクセルサイズを明示的に指定し、横スクロールで全体を見られるようにする。
    function sizeToNaturalDimensions() {
        document.querySelectorAll("pre.mermaid svg, div.mermaid svg").forEach(function (svg) {
            var viewBox = svg.viewBox && svg.viewBox.baseVal;
            if (viewBox && viewBox.width && viewBox.height) {
                svg.style.width = viewBox.width + "px";
                svg.style.height = viewBox.height + "px";
                svg.style.maxWidth = "none";
            }
        });
    }

    function init() {
        if (!window.mermaid) {
            return;
        }
        window.mermaid.initialize({
            startOnLoad: false,
            theme: "dark",
            securityLevel: "loose",
        });
        var result = window.mermaid.run();
        if (result && typeof result.then === "function") {
            result.then(sizeToNaturalDimensions).catch(sizeToNaturalDimensions);
        } else {
            sizeToNaturalDimensions();
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
