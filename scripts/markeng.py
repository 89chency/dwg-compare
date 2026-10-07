"""依 <work>/res/<idx>.json，在新圖複本（<原檔名>_比對標示.dwg，存在原檔旁，xref 才接得上）標示差異：
- 每個差異群組畫雲線框＋編號說明文字（圖層 REV-比對標示）
- 新增或修改的物件本身改成標示色
- 標示色 = cad.json 的 rev_aci；各配置指定出圖型式 cad.json 的 ctb（標示色印紅、其餘印黑）
結果寫 <work>/res/<idx>_marked.json（給 report.py / plotpdf.py）。
用法: python markeng.py --work <工作資料夾> <idx> [<idx> ...]
"""
import json, math, os, shutil, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cadcom

MARK_SUFFIX = "_比對標示"
ZH = {"LINE": "線", "LWPOLYLINE": "線", "POLYLINE": "線", "HATCH": "填充", "INSERT": "圖塊", "DIMENSION": "尺寸",
      "TEXT": "文字", "MTEXT": "文字", "CIRCLE": "圓", "ARC": "弧", "VIEWPORT": "視埠", "MULTILEADER": "引線", "SPLINE": "曲線"}

def short(lst, n=2, w=14):
    return "、".join(s.replace("\n", " ")[:w] for s in lst[:n]) + ("…" if len(lst) > n else "")

def label(c):
    at, dt, bl = c["add_text"], c["del_text"], c["blocks"]
    if at and dt: return f"改：{short(dt)} → {short(at)}"
    if bl and c["n_add"] and c["n_del"]: return f"圖塊變更：{short(bl, 1, 24)}"
    if at and not c["n_del"]: return f"新增：{short(at)}"
    if dt and not c["n_add"]: return f"刪除：{short(dt)}"
    kind = "修改" if c["n_add"] and c["n_del"] else ("新增" if c["n_add"] else "刪除")
    t = "、".join(dict.fromkeys(ZH.get(k, k) for k in {**c["add_types"], **c["del_types"]}))[:12]
    return f"{kind}{t}" + (f"（{short(bl, 1, 20)}）" if bl else "")

def note_unclouded(c):
    if c.get("unlocated"): return "（未標雲）無法定位的物件變更，需人工確認：" + label(c)
    return "（未標雲）" + ("視埠範圍調整" if c.get("vp_only") else f"整張範圍物件變更：{label(c)}")

def cloud(x1, y1, x2, y2, step):
    pts = []
    for (ax, ay, bx, by) in [(x1, y1, x2, y1), (x2, y1, x2, y2), (x2, y2, x1, y2), (x1, y2, x1, y1)]:
        n = max(1, round(math.hypot(bx - ax, by - ay) / step))
        pts += [(ax + (bx - ax) * i / n, ay + (by - ay) * i / n) for i in range(n)]
    return pts

def marked_path(newf):
    b, e = os.path.splitext(newf); return b + MARK_SUFFIX + e

def row(no, sp, c, lab):
    return {"no": no, "space": sp, "label": lab, "box": [round(v, 1) for v in c["box"]], "n_add": c["n_add"], "n_del": c["n_del"],
            "add_text": c["add_text"], "del_text": c["del_text"], "blocks": c["blocks"]}

def mark(work, idx):
    cfg = cadcom.load_cfg(work); aci = cfg["rev_aci"]
    k, oldf, newf = cadcom.read_lines(os.path.join(work, "pairs.txt"))[int(idx)]
    r = json.load(open(os.path.join(work, "res", f"{idx}.json"), encoding="utf-8"))
    outf = os.path.normpath(marked_path(newf))
    meta = {"idx": idx, "kind": k, "old": oldf, "new": newf, "marked": outf, "rows": [], "notes": [],
            "layouts_added": r["layouts_added"], "layouts_removed": r["layouts_removed"]}
    save = lambda: json.dump(meta, open(os.path.join(work, "res", f"{idx}_marked.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    cloudable = [c for sp in r["spaces"] for c in sp["clusters"] if not (c.get("vp_only") or c.get("sheetwide"))]
    if not cloudable:
        meta["marked"] = ""
        meta["rows"] = [row("-", sp["space"], c, note_unclouded(c)) for sp in r["spaces"] for c in sp["clusters"]]
        save()
        if os.path.exists(outf): os.remove(outf)   # 只刪本工具先前產生的 _比對標示 檔
        return 0

    shutil.copy2(os.path.normpath(newf), outf)
    app = cadcom.new_app(cfg)
    try:
        doc = cadcom.open_doc(app, outf, read_only=False)
        try: lyr = doc.Layers.Item(cadcom.LAYER)
        except Exception: lyr = doc.Layers.Add(cadcom.LAYER)
        lyr.Color = aci; lyr.LayerOn = True; lyr.Freeze = False; lyr.Lock = False
        try: doc.TextStyles.Item("微軟正黑體"); style = "微軟正黑體"
        except Exception:
            st = doc.TextStyles.Add("REV-微軟正黑體"); st.fontFile = "msjh.ttc"; style = "REV-微軟正黑體"
        no = 0
        for sp in r["spaces"]:
            blk = doc.ModelSpace if sp["space"] == "Model" else doc.Layouts.Item(sp["space"]).Block
            h = sp["text_h"] * 1.2
            for c in sp["clusters"]:
                if c.get("vp_only") or c.get("sheetwide"):
                    meta["rows"].append(row("-", sp["space"], c, note_unclouded(c))); continue
                no += 1
                x1, y1, x2, y2 = c["box"]; m = h * 0.8
                x1 -= m; y1 -= m; x2 += m; y2 += m
                pts = cloud(x1, y1, x2, y2, max(h * 1.2, 2 * ((x2 - x1) + (y2 - y1)) / 300))
                pl = cadcom.call(blk.AddLightWeightPolyline, cadcom.variant(*[v for p in pts for v in p])); pl.Closed = True
                for i in range(len(pts)): pl.SetBulge(i, -0.45)
                pl.Layer = cadcom.LAYER; pl.Color = aci; pl.ConstantWidth = h * 0.08
                t = cadcom.call(blk.AddText, f"{no}.{label(c)}", cadcom.variant(x2 + h * 0.5, y2 - h, 0), h)
                t.Layer = cadcom.LAYER; t.Color = aci; t.StyleName = style
                meta["rows"].append(row(no, sp["space"], c, label(c)))
        # 新增/修改的物件本身改成標示色；暫時解鎖的圖層改完再鎖回
        relock, n_fail = set(), 0
        for sp in r["spaces"]:
            for c in sp["clusters"]:
                for hd in c.get("add_handles", []):
                    try:
                        o = doc.HandleToObject(hd)
                        lay = doc.Layers.Item(o.Layer)
                        if lay.Lock: lay.Lock = False; relock.add(o.Layer)
                        o.Color = aci
                    except Exception:
                        n_fail += 1
        for name in relock: doc.Layers.Item(name).Lock = True
        if n_fail: meta["notes"].append(f"{n_fail} 個變更物件無法改色（仍有雲線框標示）")
        if doc.GetVariable("PSTYLEMODE") == 1:   # 顏色相依（CTB）模式才能指定 CTB
            for lo in doc.Layouts:
                try: lo.StyleSheet = cfg["ctb"]
                except Exception: pass
        else:
            meta["notes"].append("圖檔使用具名出圖型式（STB），未指定 CTB；PDF 可能不是黑白紅")
        cadcom.call(doc.Save); doc.Close(False)
    finally:
        cadcom.quit_app(app)
    bak = os.path.splitext(outf)[0] + ".bak"
    if os.path.exists(bak): os.remove(bak)
    save()
    return no

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--one":   # 子行程：獨立 CAD 執行個體處理一張
        print("marks", mark(sys.argv[2], sys.argv[3])); return
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--work", required=True); ap.add_argument("idx", nargs="+")
    a = ap.parse_args()
    cfg = cadcom.load_cfg(a.work)
    for idx in a.idx:
        t = time.time()
        r = json.load(open(os.path.join(a.work, "res", f"{idx}.json"), encoding="utf-8"))
        n_h = sum(len(c.get("add_handles", [])) for sp in r["spaces"] for c in sp["clusters"])
        # 逐一改色約 0.05 秒/個，變更量大的圖給較長時間
        ok, msg = cadcom.run_isolated(cfg, [os.path.abspath(__file__), "--one", a.work, idx], timeout=600 + int(n_h * 0.15))
        print(idx, msg if ok else "FAIL " + msg, f"{time.time()-t:.0f}s", flush=True)

if __name__ == "__main__":
    main()
