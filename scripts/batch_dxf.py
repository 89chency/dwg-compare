"""把 pairs.txt 的新舊 DWG 轉成 <work>/dxf/<idx>_old|new.dxf（唯讀開啟，原檔不動）。
- 快取：每個 DXF 旁存 .src（來源路徑|大小|修改時間），一致才沿用，避免配對變動或圖檔更新後誤用舊 DXF
- 每個檔在子行程以獨立 CAD 執行個體轉檔並設逾時（CAD 當掉會跳「崩潰報告」，COM 會永久卡住）
用法: python batch_dxf.py --work <工作資料夾> [--timeout 300]
"""
import argparse, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cadcom

def fingerprint(src):
    st = os.stat(src)
    return f"{os.path.normcase(os.path.abspath(src))}|{st.st_size}|{st.st_mtime_ns}"

def convert_one(work, src, out):
    cfg = cadcom.load_cfg(work); app = cadcom.new_app(cfg)
    try:
        d = cadcom.open_doc(app, src)
        cadcom.call(d.SaveAs, out, cadcom.DXF_SAVE_TYPE); d.Close(False)
    finally:
        cadcom.quit_app(app)

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--one":
        return convert_one(*sys.argv[2:5])
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True); ap.add_argument("--timeout", type=int, default=300)
    a = ap.parse_args()
    cfg = cadcom.load_cfg(a.work)
    pairs = cadcom.read_lines(os.path.join(a.work, "pairs.txt"))
    os.makedirs(os.path.join(a.work, "dxf"), exist_ok=True)
    log = open(os.path.join(a.work, "dxf_log.txt"), "a", encoding="utf-8")
    for i, (k, o, n) in enumerate(pairs):
        for tag, f in (("old", o), ("new", n)):
            out = os.path.join(a.work, "dxf", f"{i:02d}_{tag}.dxf"); src = out + ".src"
            fp = fingerprint(f)
            if os.path.exists(out) and os.path.exists(src) and open(src, encoding="utf-8").read() == fp:
                continue
            for p in (out, src):
                if os.path.exists(p): os.remove(p)
            t = time.time()
            ok, msg = cadcom.run_isolated(cfg, [os.path.abspath(__file__), "--one", a.work, f, out], timeout=a.timeout)
            ok = ok and os.path.exists(out)
            if ok: open(src, "w", encoding="utf-8").write(fp)
            line = f"{i:02d} {tag} {'ok' if ok else 'FAIL ' + msg[-200:]} {time.time()-t:.0f}s {os.path.basename(f)}"
            log.write(line + "\n"); log.flush(); print(line, flush=True)

if __name__ == "__main__":
    main()
