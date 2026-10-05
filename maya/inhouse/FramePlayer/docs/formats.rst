対応形式
========

動画は Windows の Media Foundation で読みます(デコードは Windows に任せ、外部のライブラリは使いません)。
Windows に入っている映像のデコーダーは、すべてコマ番号(順・逆・飛び飛び)と色を確かめてあります。
連番画像の形式は :doc:`sequences` を見てください。

動画
----

.. list-table::
   :header-rows: 1
   :widths: 28 32 40

   * - コーデック
     - 確かめた入れ物
     - 必要なもの
   * - H.264
     - mp4・mov・mkv・ts・m2ts・avi・3gp
     - Windows 標準(N エディションはメディア機能パック)
   * - HEVC(H.265、8bit・10bit・HDR)
     - mp4・mkv・ts
     - HEVC Video Extensions
   * - AV1(8bit・10bit)
     - mp4・mkv・webm
     - AV1 Video Extension
   * - VP9(8bit・10bit・HDR)
     - mp4・webm・mkv
     - VP9 Video Extensions
   * - VP8
     - webm・mkv
     - VP9 Video Extensions(VP8 も含みます)
   * - MPEG-2
     - mpg・ts・vob
     - MPEG-2 Video Extension
   * - MPEG-1
     - mpg
     - Windows 標準
   * - MPEG-4 Part 2(Simple Profile)・H.263
     - mp4・mov・avi・3gp
     - Windows 標準
   * - MS-MPEG4 v2・v3
     - avi
     - Windows 標準
   * - WMV7・WMV8
     - wmv
     - Windows 標準
   * - MJPEG
     - avi・mov
     - Windows 標準
   * - DV(NTSC)
     - avi
     - Windows 標準
   * - Theora
     - mkv
     - Web Media Extensions

拡張機能
--------

「必要なもの」の拡張機能は、Microsoft Store から無料で入れられます。入っていなくても FramePlayer は使えますが、
その形式だけが開けません(「Cannot set the output format」と表示します)。

入っているかは、PowerShell で ``Get-AppxPackage *VP9*``(HEVC なら ``*HEVC*``)のように確かめられます。
セットアップは、拡張機能が入っていない形式を関連付けません(:doc:`install`)。

読めないもの
------------

* ProRes(Windows にデコーダーがありません)。
* MPEG-4 Part 2 の B フレーム(XviD・DivX の多くの設定)。Windows のデコーダーが対応していません。
* mov に入った DV、ogg・ogv(Theora は mkv なら読めます)。
* 映像だけの短い(数秒の)mpg・vob。Windows が開けません(音声があるか、長ければ開けます)。

開くときの時間
--------------

* mp4・mov は、ファイルの中の目次を直接読むので、長い動画でもすぐ開きます(4K 60fps・1時間で約1秒)。
* ほかの形式は、圧縮されたままのコマを最後まで読んで目次を作ります。
* MPEG-1・MPEG-2(mpg・ts・vob)は、コマの時刻が一部にしか無いため、全体をデコードして目次を作ります(開くのに時間がかかります)。
