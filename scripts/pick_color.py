"""挑標示色並產生出圖型式（CTB）。
標示色要是「新圖完全沒用到」的 ACI，出圖時才能只讓標示印紅、其餘全黑。
產生 <out>/REV_mono_red<ACI>.ctb：該 ACI 印純紅、其餘 255 色一律印黑（線寬依物件）。
結果寫回 <work>/cad.json 的 rev_aci / ctb。
用法: python pick_color.py --work <工作資料夾> --out <輸出資料夾>
"""
import argparse, hashlib, os, sys
import ezdxf
from ezdxf import recover
from ezdxf.addons import acadctb

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import batch_dxf, cadcom

# 優先用紅色系（CAD 螢幕上看起來也偏紅），再退到其他色
PREFER = [16, 17, 18, 19, 14, 15, 12, 13, 11, 10] + list(range(240, 250)) + list(range(20, 240)) + list(range(250, 256))

def _load(f):
    try: return ezdxf.readfile(f)
    except Exception:
        d, _ = recover.readfile(f); return d

def _colors_and_xrefs(dxf, src_dwg):
    """回傳（用到的 ACI 集合, 引用的 xref DWG 絕對路徑清單）。"""
    d = _load(dxf); used = set(); xrefs = []
    for e in d.entitydb.values():
        try:
            if e.dxf.hasattr("color"): used.add(abs(e.dxf.get("color")))
        except Exception: pass
    for b in d.blocks:
        if b.block_record.is_xref:
            p = b.block.dxf.get("xref_path", "")
            full = os.path.normpath(p if os.path.isabs(p) else os.path.join(os.path.dirname(src_dwg), p))
            if os.path.exists(full): xrefs.append(full)
    return used, xrefs

def used_colors(work):
    """新圖＋它們引用的 xref（例如圖框）用到的所有 ACI；xref 內容也會出現在 PDF 上，不能撞色。"""
    cfg = cadcom.load_cfg(work)
    pairs = cadcom.read_lines(os.path.join(work, "pairs.txt"))
    have = {}   # 已有 DXF 的 DWG → DXF
    for i, (_, _, n) in enumerate(pairs):
        f = os.path.join(work, "dxf", f"{i:02d}_new.dxf")
        if os.path.exists(f): have[os.path.normcase(os.path.normpath(n))] = (f, n)
    used, seen, queue = set(), set(), list(have.values())
    for depth in range(4):   # xref 最多追 3 層
        nxt = []
        for dxf, src in queue:
            if src in seen: continue
            seen.add(src)
            u, xrefs = _colors_and_xrefs(dxf, src); used |= u
            for x in xrefs:
                key = os.path.normcase(x)
                if key in have: nxt.append(have[key]); continue
                out = os.path.join(work, "dxf", "xref_" + hashlib.md5(key.encode("utf-8")).hexdigest()[:12] + ".dxf")
                fp = batch_dxf.fingerprint(x)
                if not (os.path.exists(out) and os.path.exists(out + ".src") and open(out + ".src", encoding="utf-8").read() == fp):
                    ok, msg = cadcom.run_isolated(cfg, [os.path.join(HERE, "batch_dxf.py"), "--one", work, x, out], timeout=300)
                    if not (ok and os.path.exists(out)):
                        print(f"⚠️ xref 轉檔失敗，未納入用色檢查：{x}（{msg}）"); continue
                    open(out + ".src", "w", encoding="utf-8").write(fp)
                have[key] = (out, x); nxt.append((out, x))
        queue = nxt
    return used

def make_ctb(path, aci):
    ctb = acadctb.new_ctb()
    ctb.description = f"dwg-compare: ACI {aci} plots red, all other colors black"
    for i in range(1, 256):
        st = ctb[i]; st.color = (255, 0, 0) if i == aci else (0, 0, 0); st.grayscale = False
    ctb.save(path)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    cfg = cadcom.load_cfg(a.work)
    used = used_colors(a.work)
    aci = next((c for c in PREFER if c not in used), None)
    if aci is None: sys.exit("新圖用遍了 255 種顏色，找不到可當標示色的 ACI")
    os.makedirs(a.out, exist_ok=True)
    name = f"REV_mono_red{aci}.ctb"
    make_ctb(os.path.join(a.out, name), aci)
    cfg.update(rev_aci=aci, ctb=name); cadcom.save_cfg(a.work, cfg)
    print(f"標示色 ACI {aci}；出圖型式 {os.path.join(a.out, name)}")

if __name__ == "__main__":
    main()
