"""回歸測試：Codex 第一輪指出的漏判情境，皆須被判為有差異；完全相同者須為零差異。"""
import ezdxf, os, sys, math, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import diffeng
S = tempfile.mkdtemp(prefix="dwgc_test_")
os.makedirs(os.path.join(S, "dxf"), exist_ok=True)
def build(idx, f_old, f_new):
    for tag, f in (("old", f_old), ("new", f_new)):
        d = ezdxf.new(); f(d); d.saveas(f"{S}/dxf/{idx}_{tag}.dxf")
    r = diffeng.run(idx, S)
    return sum(c["n_add"] + c["n_del"] for sp in r["spaces"] for c in sp["clusters"])
def base(d): d.modelspace().add_text("REF", dxfattribs={"insert": (0, 0), "height": 2.5})
cases = {
 "same":    (lambda d: (base(d), d.modelspace().add_line((0,0),(10,0))), lambda d: (base(d), d.modelspace().add_line((10,0),(0,0))), False),
 "ellipse": (lambda d: (base(d), d.modelspace().add_ellipse((0,0),(10,0),0.5)), lambda d: (base(d), d.modelspace().add_ellipse((0,0),(10,0),0.5,0,math.pi)), True),
 "textrot": (lambda d: (base(d), d.modelspace().add_text("A", dxfattribs={"insert":(5,5),"height":2.5})), lambda d: (base(d), d.modelspace().add_text("A", dxfattribs={"insert":(5,5),"height":2.5,"rotation":90})), True),
 "ltype":   (lambda d: (base(d), d.modelspace().add_line((0,0),(10,0))), lambda d: (base(d), d.modelspace().add_line((0,0),(10,0),dxfattribs={"linetype":"DASHED"})), True),
}
def hsq(d):
    base(d); h = d.modelspace().add_hatch(); h.paths.add_polyline_path([(0,0),(10,0),(10,10),(0,10)])
def htri(d):
    base(d); h = d.modelspace().add_hatch(); h.paths.add_polyline_path([(0,0),(10,0),(10,10)])
cases["hatch"] = (hsq, htri, True)
def hsq2(d):  # 同一方形：起點不同、反向、多一個共線點 → 應視為相同
    base(d); h = d.modelspace().add_hatch(); h.paths.add_polyline_path([(10,10),(10,0),(5,0),(0,0),(0,10)])
cases["hatchsame"] = (hsq, hsq2, False)
def xr(path):
    def f(d):
        base(d); d.add_xref_def(path, "XR"); d.modelspace().add_blockref("XR", (0, 0))
    return f
cases["xrefpath"] = (xr(r".\X-PLAN_v1.dwg"), xr(r".\X-PLAN_v2.dwg"), True)
cases["xrefsame"] = (xr(r"..\old\X-PLAN.dwg"), xr(r"..\new\X-PLAN.dwg"), False)
# 第二輪審查情境
def lay(lt):
    def f(d):
        base(d)
        d.layers.add("W", linetype=lt)
        d.modelspace().add_line((0, 0), (10, 0), dxfattribs={"layer": "W"})
    return f
cases["layerlt"] = (lay("CONTINUOUS"), lay("DASHED"), True)
def blkbase(bp):
    def f(d):
        base(d); b = d.blocks.new("B", base_point=bp); b.add_line((0, 0), (5, 0)); d.modelspace().add_blockref("B", (20, 20))
    return f
cases["blkbase"] = (blkbase((0, 0)), blkbase((100, 0)), True)
def aligned(p2):
    def f(d):
        base(d); d.modelspace().add_text("AL", dxfattribs={"height": 2.5}).set_placement((0, 0), p2, align=ezdxf.enums.TextEntityAlignment.ALIGNED)
    return f
cases["textalign"] = (aligned((10, 0)), aligned((100, 0)), True)
def hscale(sc):
    def f(d):
        base(d); h = d.modelspace().add_hatch(); h.set_pattern_fill("ANSI31", scale=sc); h.paths.add_polyline_path([(0, 0), (10, 0), (10, 10), (0, 10)])
    return f
cases["hatchscale"] = (hscale(1), hscale(10), True)
def spl(y):
    def f(d):
        base(d); d.modelspace().add_spline(fit_points=[(0, 0), (5, y), (10, 0)])
    return f
cases["splinefit"] = (spl(5), spl(15), True)
cases["zerosize"] = (lambda d: None, lambda d: d.modelspace().add_point((3, 3)), True)
ok = True
for k, (fo, fn, expect) in cases.items():
    n = build("t_" + k, fo, fn); got = n > 0
    print(f"{k:9s} diff={n:2d} expect={'有差異' if expect else '無差異'} {'PASS' if got == expect else 'FAIL'}")
    ok &= got == expect
print("ALL PASS" if ok else "SOME FAIL")
sys.exit(0 if ok else 1)
