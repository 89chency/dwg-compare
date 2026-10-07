"""比對舊/新 DXF，輸出差異群組 JSON（座標以新圖為準）。
用法: python diffeng.py --work <工作資料夾> <idx> [<idx> ...]
      <work>/dxf/<idx>_old.dxf, <idx>_new.dxf → <work>/res/<idx>.json
"""
import ezdxf, sys, os, json, math, collections, hashlib, statistics
from ezdxf import bbox, recover, path as epath

RD = 1  # 座標取到小數 1 位

def P(v, n=RD):
    v = tuple(v)
    return (round(v[0], n), round(v[1], n))

def load(path):
    try:
        return ezdxf.readfile(path)
    except Exception:
        d, _ = recover.readfile(path)
        return d

def txt(e):
    t = e.dxftype()
    try:
        if t == "TEXT": return e.dxf.text.strip()
        if t == "MTEXT": return e.plain_text().strip()
        if t in ("ATTRIB", "ATTDEF"): return e.dxf.text.strip()
        if t == "INSERT": return " ".join(a.dxf.text.strip() for a in e.attribs if a.dxf.text.strip())
        if t == "MULTILEADER":
            c = e.context.mtext
            return (c.default_content if c else "").strip()
    except Exception:
        pass
    return ""

def norm_loop(pts):
    """封閉邊界正規化：Revit 等匯出時起點、方向、共線點常不同，但形狀相同。"""
    q = []
    for p in pts:
        if not q or p != q[-1]: q.append(p)
    if len(q) > 1 and q[0] == q[-1]: q.pop()
    changed = True
    while changed and len(q) > 3:
        changed = False
        for i in range(len(q)):
            a, b, c = q[i - 1], q[i], q[(i + 1) % len(q)]
            if abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) < 1e-6:
                q.pop(i); changed = True; break
    area = abs(sum(q[i - 1][0] * q[i][1] - q[i][0] * q[i - 1][1] for i in range(len(q)))) / 2
    return (tuple(sorted(set(q))), round(area))

class Sig:
    def __init__(self, doc):
        self.doc = doc
        self.bh = {}

    def block_hash(self, name):
        if name in self.bh: return self.bh[name]
        self.bh[name] = "recursion"
        blk = self.doc.blocks.get(name)
        if blk is None: h = "missing"
        elif blk.block_record.is_xref:
            # 外參比對路徑檔名（新舊資料夾不同，不比完整路徑）；外參圖本身另列一組比對
            h = "xref:" + name + ":" + os.path.basename(blk.block.dxf.get("xref_path", "").replace("\\", "/")).lower()
        else:
            items = sorted(str(self.sig(e)) for e in blk) + ["base:" + str(P(blk.block.dxf.get("base_point", (0, 0))))]
            h = hashlib.md5("\n".join(items).encode("utf-8", "replace")).hexdigest()
        self.bh[name] = h
        return h

    def sig(self, e):
        return self._sig(e) + (self.ltype(e),)

    def ltype(self, e):
        lt = e.dxf.get("linetype", "BYLAYER").upper()
        if lt == "BYLAYER":
            lay = self.doc.layers.get(e.dxf.get("layer", "0"))
            lt = "L:" + (lay.dxf.get("linetype", "CONTINUOUS").upper() if lay is not None else "?")
        return lt

    def _sig(self, e):
        t = e.dxftype(); d = e.dxf
        try:
            if t == "LINE": return (t,) + tuple(sorted([P(d.start), P(d.end)]))
            if t == "LWPOLYLINE": return (t, e.closed, tuple(P(p) for p in e.get_points("xy")), tuple(round(b, 2) for b in (p[4] for p in e.get_points())))
            if t == "POLYLINE": return (t, e.is_closed, tuple(P(v.dxf.location) for v in e.vertices))
            if t == "CIRCLE": return (t, P(d.center), round(d.radius, RD))
            if t == "ARC": return (t, P(d.center), round(d.radius, RD), round(d.start_angle, 1), round(d.end_angle, 1))
            if t == "ELLIPSE": return (t, P(d.center), P(d.major_axis), round(d.ratio, 3), round(d.start_param, 3), round(d.end_param, 3))
            if t == "TEXT":
                al = (d.get("halign", 0), d.get("valign", 0))
                return (t, P(d.insert), txt(e), round(d.height, 1), round(d.get("rotation", 0), 1), al,
                        P(d.get("align_point", (0, 0))) if al != (0, 0) else None)
            if t == "MTEXT": return (t, P(d.insert), txt(e), round(d.char_height, 1), round(d.get("rotation", 0), 1))
            if t == "INSERT":
                att = tuple(sorted((a.dxf.tag, a.dxf.text) for a in e.attribs))
                nm = ""  # 匿名/動態/Revit 匯出圖塊名稱每次存檔會變，只比內容
                return (t, nm, P(d.insert), round(d.xscale, 3), round(d.yscale, 3), round(d.rotation, 1), att, self.block_hash(d.name))
            if t == "DIMENSION":
                m = None
                try: m = round(e.get_measurement(), 1)
                except Exception: pass
                return (t, P(d.defpoint), P(d.get("defpoint2", (0, 0))), P(d.get("defpoint3", (0, 0))), d.get("text", ""), m)
            if t == "HATCH":
                # 邊界形狀：每條邊界正規化（去重複/共線點、不論起點與方向）後取頂點集合＋面積
                bnd = tuple(sorted(norm_loop([P(v, 0) for v in pa.flattening(1)]) for pa in epath.from_hatch(e)))
                return (t, d.pattern_name, round(d.get("pattern_scale", 1), 3), round(d.get("pattern_angle", 0), 1),
                        hashlib.md5(str(bnd).encode()).hexdigest())
            if t == "SPLINE": return (t, tuple(P(p) for p in e.control_points), tuple(P(p) for p in e.fit_points), d.get("degree", 3))
            if t == "SOLID": return (t, P(d.vtx0), P(d.vtx1), P(d.vtx2), P(d.vtx3))
            if t == "POINT": return (t, P(d.location))
            if t == "VIEWPORT": return (t, P(d.center), round(d.width, 1), round(d.height, 1), P(d.view_center_point), round(d.view_height, 1))
            if t == "MULTILEADER": return (t, txt(e), P(e.context.base_point) if e.context else None)
            if t == "LEADER": return (t, tuple(P(v) for v in e.vertices))
        except Exception:
            pass
        b = bbox.extents([e], fast=True)
        return (t, P(b.extmin, 0), P(b.extmax, 0)) if b.has_data else (t, d.handle)

def eff(doc, name):
    if not name.startswith("*"): return name
    br = doc.block_records.get(name)
    try:
        for app, tags in (br.xdata.data.items() if br.xdata else []):
            if app == "AcDbBlockRepBTag":
                h = [t.value for t in tags if t.code == 1005][0]; return doc.entitydb[h].dxf.name
    except Exception:
        pass
    return name

def ebox(e):
    try:
        b = bbox.extents([e], fast=True)
        if b.has_data: return [b.extmin.x, b.extmin.y, b.extmax.x, b.extmax.y]
    except Exception:
        pass
    for k in ("insert", "location", "center", "start", "defpoint"):
        if e.dxf.hasattr(k):
            v = e.dxf.get(k); return [v[0], v[1], v[0], v[1]]
    return None

def is_field(e):
    # 圖框圖號/圖名多為欄位，DWG 只存最後一次更新的快取值，比對會誤判
    try:
        return e.has_extension_dict and "ACAD_FIELD" in e.get_extension_dict()
    except Exception:
        return False

def spaces(doc):
    out = {"Model": doc.modelspace()}
    for lay in doc.layouts:
        if lay.name != "Model": out[lay.name] = lay
    return out

def cluster(items, gap):
    # items: list of dict with box; 以 gap 擴張後重疊者合併
    n = len(items); par = list(range(n))
    def f(i):
        while par[i] != i: par[i] = par[par[i]]; i = par[i]
        return i
    order = sorted(range(n), key=lambda i: items[i]["box"][0])
    active = []
    for i in order:
        b = items[i]["box"]
        active = [j for j in active if items[j]["box"][2] + gap >= b[0] - gap]
        for j in active:
            c = items[j]["box"]
            if c[0] - gap <= b[2] + gap and c[1] - gap <= b[3] + gap and b[1] - gap <= c[3] + gap:
                par[f(i)] = f(j)
        active.append(i)
    g = collections.defaultdict(list)
    for i in range(n): g[f(i)].append(items[i])
    return list(g.values())

def run(idx, work):
    do = load(os.path.join(work, "dxf", f"{idx}_old.dxf")); dn = load(os.path.join(work, "dxf", f"{idx}_new.dxf"))
    so, sn = Sig(do), Sig(dn)
    spo, spn = spaces(do), spaces(dn)
    res = {"idx": idx, "spaces": [], "layouts_added": [k for k in spn if k not in spo], "layouts_removed": [k for k in spo if k not in spn]}
    for name, lay in spn.items():
        if name not in spo: continue
        mo = collections.defaultdict(list); mn = collections.defaultdict(list)
        for e in spo[name]:
            if not is_field(e): mo[so.sig(e)].append(e)
        for e in lay:
            if not is_field(e): mn[sn.sig(e)].append(e)
        items = []
        for k, es in mn.items():
            extra = len(es) - len(mo.get(k, []))
            for e in es[:max(0, extra)]:
                items.append({"kind": "add", "type": e.dxftype(), "text": txt(e), "box": ebox(e), "layer": e.dxf.layer, "h": e.dxf.handle,
                              "blk": eff(dn, e.dxf.name) if e.dxftype() == "INSERT" else ""})
        for k, es in mo.items():
            extra = len(es) - len(mn.get(k, []))
            for e in es[:max(0, extra)]:
                items.append({"kind": "del", "type": e.dxftype(), "text": txt(e), "box": ebox(e), "layer": e.dxf.layer,
                              "blk": eff(do, e.dxf.name) if e.dxftype() == "INSERT" else ""})
        unloc = [i for i in items if not i["box"]]
        items = [i for i in items if i["box"]]
        if not items and not unloc:
            continue
        ext = bbox.extents(lay, fast=True)
        diag = math.hypot(ext.size.x, ext.size.y) if ext.has_data else 1000
        th = [e.dxf.height for e in lay.query("TEXT") if e.dxf.height > 0][:2000]
        h = statistics.median(th) if th else diag * 0.003
        if h <= 0: h = 1.0  # 零尺寸圖面（如僅一個點）避免除以零
        isbig = lambda i: math.hypot(i["box"][2] - i["box"][0], i["box"][3] - i["box"][1]) > h * 80
        big = [i for i in items if isbig(i)]
        small = [i for i in items if not isbig(i)]
        groups = cluster(small, gap=h * 4) + [[b] for b in big]
        cl = []
        for g in groups:
            box = [min(i["box"][0] for i in g), min(i["box"][1] for i in g), max(i["box"][2] for i in g), max(i["box"][3] for i in g)]
            add = [i for i in g if i["kind"] == "add"]; dele = [i for i in g if i["kind"] == "del"]
            area = lambda b: max(0, b[2] - b[0]) * max(0, b[3] - b[1])
            sheetwide = ext.has_data and area(box) > 0.5 * ext.size.x * ext.size.y
            vp_only = all(i["type"] == "VIEWPORT" for i in g)
            cl.append({"box": box, "sheetwide": bool(sheetwide), "vp_only": vp_only, "n_add": len(add), "n_del": len(dele),
                       "add_text": [i["text"] for i in add if i["text"]], "del_text": [i["text"] for i in dele if i["text"]],
                       "add_types": dict(collections.Counter(i["type"] for i in add)),
                       "del_types": dict(collections.Counter(i["type"] for i in dele)),
                       "blocks": sorted({i["blk"] for i in g if i["blk"] and not i["blk"].startswith("*")}),
                       "add_handles": [i["h"] for i in add if i.get("h")]})
        cl.sort(key=lambda c: (-round(c["box"][3] / (h * 50)), c["box"][0]))  # 由上而下、由左而右
        if unloc:  # 無法定位者不畫雲線，但明確列出供人工確認
            cl.append({"box": [0, 0, 0, 0], "sheetwide": True, "vp_only": False, "unlocated": True,
                       "n_add": sum(i["kind"] == "add" for i in unloc), "n_del": sum(i["kind"] == "del" for i in unloc),
                       "add_text": [i["text"] for i in unloc if i["kind"] == "add" and i["text"]],
                       "del_text": [i["text"] for i in unloc if i["kind"] == "del" and i["text"]],
                       "add_types": dict(collections.Counter(i["type"] for i in unloc if i["kind"] == "add")),
                       "del_types": dict(collections.Counter(i["type"] for i in unloc if i["kind"] == "del")),
                       "blocks": sorted({i["blk"] for i in unloc if i["blk"]})})
        res["spaces"].append({"space": name, "text_h": h, "diag": diag, "clusters": cl})
    os.makedirs(os.path.join(work, "res"), exist_ok=True)
    json.dump(res, open(os.path.join(work, "res", f"{idx}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return res

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--work", required=True); ap.add_argument("idx", nargs="+")
    a = ap.parse_args()
    for idx in a.idx:
        try:
            r = run(idx, a.work)
        except Exception as e:   # 單張失敗不中斷整批；沒有結果檔的圖，Excel 會標為需人工比對
            print(f"{idx} FAIL {type(e).__name__}: {e}", flush=True); continue
        n_add = sum(c["n_add"] for sp in r["spaces"] for c in sp["clusters"])
        n_del = sum(c["n_del"] for sp in r["spaces"] for c in sp["clusters"])
        print(f"{idx} 群組 {sum(len(sp['clusters']) for sp in r['spaces'])} 新增 {n_add} 刪除 {n_del}"
              f" 新增配置 {r['layouts_added']} 刪除配置 {r['layouts_removed']}", flush=True)
