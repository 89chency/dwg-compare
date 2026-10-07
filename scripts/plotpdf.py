"""把 _比對標示.dwg 出成 PDF（cad.json 的 ctb：標示色印紅、其餘全黑）。
- 每個配置一頁（A3 橫式、範圍、縮放至圖紙）
- 模型空間的標示依位置分區（約一層樓一區），每區一頁 A1 視窗出圖；上限 40 頁
- 空白頁自動略過；合併為 <out>/<圖名>_比對標示.pdf
前提：ctb 已放進 CAD 的出圖型式資料夾（run_all.py --install-ctb）。
用法: python plotpdf.py --work <工作資料夾> --out <PDF 資料夾> <idx 或 marked.json> [...]
"""
import json, os, shutil, sys, tempfile, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cadcom

A3 = ["ISO_full_bleed_A3_(420.00_x_297.00_MM)", "ISO_A3_(420.00_x_297.00_MM)"]
A1L = ["ISO_full_bleed_A1_(841.00_x_594.00_MM)", "ISO_A1_(841.00_x_594.00_MM)"]
A1P = ["ISO_full_bleed_A1_(594.00_x_841.00_MM)", "ISO_A1_(594.00_x_841.00_MM)"]
MAX_PAGES = 40

def setup(lay, cfg, medias, ptype, use_ctb=True):
    lay.ConfigName = cfg["pc3"]
    names = list(lay.GetCanonicalMediaNames())
    lay.CanonicalMediaName = next((m for m in medias if m in names), next((m for m in A3 if m in names), names[0]))
    if use_ctb:   # 具名出圖型式（STB）模式的圖檔不能指定 CTB，改用圖檔原本的出圖型式
        try: lay.StyleSheet = cfg["ctb"]; lay.PlotWithPlotStyles = True
        except Exception: pass
    lay.PlotType = ptype            # 1=範圍 4=視窗
    lay.PlotRotation = 0            # 搭配寬 x 高的圖紙名稱 = 橫式
    lay.UseStandardScale = True; lay.StandardScale = 0; lay.CenterPlot = True   # 縮放至圖紙

def regions(boxes, h):
    """標示框單一連結分群；群數過多就放寬間距。回傳每區視窗 (x1,y1,x2,y2)。"""
    gap = 100 * h
    while True:
        groups = [list(b) for b in boxes]; merged = True
        while merged:
            merged = False; out = []
            for b in groups:
                for o in out:
                    if b[0] - gap <= o[2] and o[0] - gap <= b[2] and b[1] - gap <= o[3] and o[1] - gap <= b[3]:
                        o[:] = [min(o[0], b[0]), min(o[1], b[1]), max(o[2], b[2]), max(o[3], b[3])]; merged = True; break
                else: out.append(b)
            groups = out
        if len(groups) <= MAX_PAGES: break
        gap *= 2
    pad = lambda b: max(50 * h, 0.15 * max(b[2] - b[0], b[3] - b[1]))
    return [(b[0] - pad(b), b[1] - pad(b), b[2] + pad(b), b[3] + pad(b)) for b in sorted(groups, key=lambda b: (-b[3], b[0]))]

def plot(doc, cfg, f):
    return cadcom.call(doc.Plot.PlotToFile, f, cfg["pc3"]) and os.path.exists(f)

def plot_one(work, mj, outdir):
    import pymupdf
    cfg = cadcom.load_cfg(work)
    m = json.load(open(mj, encoding="utf-8"))
    if not m.get("marked") or not os.path.exists(m["marked"]): return "無標示，略過"
    model_rows = [r for r in m["rows"] if r["space"] == "Model" and r["no"] != "-"]
    tmp = tempfile.mkdtemp(prefix="dwgc_pdf_"); pages = []
    app = cadcom.new_app(cfg)
    try:
        doc = cadcom.open_doc(app, m["marked"])
        doc.SetVariable("BACKGROUNDPLOT", 0)
        ctb_ok = doc.GetVariable("PSTYLEMODE") == 1
        lays = sorted([l for l in doc.Layouts if l.Name != "Model"], key=lambda l: l.TabOrder)
        for k, lay in enumerate(lays):
            doc.ActiveLayout = lay; setup(lay, cfg, A3, 1, ctb_ok)
            f = os.path.join(tmp, f"{k:03d}.pdf")
            if plot(doc, cfg, f): pages.append(f)
        if model_rows or not lays:
            lay = doc.Layouts.Item("Model"); doc.ActiveLayout = lay
            # 圖檔若存在 3D 視角，視窗座標會被當成視圖座標而出成空白 → 先切平面視圖（唯讀開啟，不存檔）
            vp = doc.ActiveViewport; vp.Direction = cadcom.variant(0, 0, 1); vp.Target = cadcom.variant(0, 0, 0); doc.ActiveViewport = vp
            app.ZoomExtents()
            rj = os.path.join(work, "res", f"{m['idx']}.json")
            h = next((sp["text_h"] for sp in json.load(open(rj, encoding="utf-8"))["spaces"] if sp["space"] == "Model"), 1.0)
            wins = regions([r["box"] for r in model_rows], h) if model_rows else []
            if not wins:
                setup(lay, cfg, A1L, 1, ctb_ok); f = os.path.join(tmp, "zz_model.pdf")
                if plot(doc, cfg, f): pages.append(f)
            for k, (x1, y1, x2, y2) in enumerate(wins):
                setup(lay, cfg, A1L if (x2 - x1) >= (y2 - y1) else A1P, 1, ctb_ok)   # 先設範圍，再給視窗並切換（順序反了會報參數錯誤）
                lay.SetWindowToPlot(cadcom.variant(x1, y1), cadcom.variant(x2, y2)); lay.PlotType = 4
                f = os.path.join(tmp, f"zz_model_{k:03d}.pdf")
                if plot(doc, cfg, f): pages.append(f)
        doc.Close(False)
    finally:
        cadcom.quit_app(app)
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, os.path.splitext(os.path.basename(m["marked"]))[0] + ".pdf")
    pdf = pymupdf.open()
    for p in pages:
        src = pymupdf.open(p)
        if any(len(pg.get_drawings()) or pg.get_text().strip() for pg in src): pdf.insert_pdf(src)   # 略過空白頁
    n = len(pdf)
    if n: pdf.save(out)
    shutil.rmtree(tmp, ignore_errors=True)
    note = "" if ctb_ok else "（圖檔為 STB 出圖型式，未套黑白紅）"
    return f"{n} 頁 {out}{note}" if n else "沒有可出圖的頁面"

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--one":
        print(plot_one(sys.argv[2], sys.argv[3], sys.argv[4])); return
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--work", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("items", nargs="+", help="idx 或 *_marked.json 路徑")
    a = ap.parse_args()
    cfg = cadcom.load_cfg(a.work)
    for it in a.items:
        mj = it if it.endswith(".json") else os.path.join(a.work, "res", f"{it}_marked.json")
        if not os.path.exists(mj): continue
        t = time.time()
        ok, msg = cadcom.run_isolated(cfg, [os.path.abspath(__file__), "--one", a.work, mj, a.out], timeout=900)
        print(os.path.basename(mj), ("ok " if ok else "FAIL ") + msg[-160:], f"{time.time()-t:.0f}s", flush=True)

if __name__ == "__main__":
    main()
