"""環境檢查：比對前必跑。檢查通過才寫 <work>/cad.json 供其他腳本使用。

用法:
  python env_check.py --work <工作資料夾> [--engine auto|bricscad|autocad] [--sample <新版圖說資料夾>] [--full]
  --sample：檢查圖檔 DWG 格式，確認選到的 CAD 打得開
  --full  ：實際啟動 CAD，確認 COM 自動化、PDF 印表機、出圖型式資料夾（約 30～60 秒）
結束碼：0 = 可以開始比對；1 = 有必須處理的問題
"""
import argparse, glob, importlib, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cadcom

# AutoCAD 主版號 → 年份（R22 = 2018，才能開 2018 格式 DWG）
ACAD_YEAR = {19: "2013/2014", 20: "2015/2016", 21: "2017", 22: "2018", 23: "2019/2020", 24: "2021～2024", 25: "2025/2026", 26: "2027"}
DWG_FMT = {"AC1032": ("2018", 22, 18), "AC1027": ("2013", 19, 13), "AC1024": ("2010", 18, 10),
           "AC1021": ("2007", 17, 8), "AC1018": ("2004", 16, 4), "AC1015": ("2000", 15, 1),
           "AC1014": ("R14", 15, 1), "AC1012": ("R13", 15, 1), "AC1009": ("R11/R12", 15, 1)}  # 格式: (名稱, AutoCAD 最低主版, BricsCAD 最低版)
PKGS = [("ezdxf", "ezdxf"), ("win32com.client", "pywin32"), ("openpyxl", "openpyxl"), ("pymupdf", "pymupdf")]

rows, fatal = [], []
def report(ok, item, detail, must=True):
    rows.append(("✅" if ok else ("❌" if must else "⚠️"), item, detail))
    if not ok and must: fatal.append(item)

def reg_versions(prefix):
    """列出 HKCR 下已註冊的 <prefix>.<版本> ProgID。"""
    import winreg
    out, i = [], 0
    while True:
        try: name = winreg.EnumKey(winreg.HKEY_CLASSES_ROOT, i)
        except OSError: break
        i += 1
        m = re.fullmatch(re.escape(prefix) + r"\.(\d+)(?:\.\d+)?", name)
        if m: out.append((int(m.group(1)), name))
    return sorted(set(out))

def has_lt():
    import winreg
    for root in (r"SOFTWARE\Autodesk\AutoCAD LT", r"SOFTWARE\WOW6432Node\Autodesk\AutoCAD LT"):
        try: winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, root); return True
        except OSError: pass
    return False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--engine", default="auto", choices=["auto", "bricscad", "autocad"])
    ap.add_argument("--sample")
    ap.add_argument("--full", action="store_true")
    a = ap.parse_args()

    # 1. 作業系統 / Python
    report(sys.platform == "win32", "作業系統", "Windows" if sys.platform == "win32" else f"{sys.platform}（需要 Windows：CAD 自動化只能在 Windows 上執行）")
    report(sys.version_info >= (3, 9), "Python", sys.version.split()[0] + ("" if sys.version_info >= (3, 9) else "（需要 3.9 以上）"))
    # 2. 套件
    missing = []
    for mod, pip in PKGS:
        try: importlib.import_module(mod); report(True, f"套件 {pip}", "已安裝")
        except Exception: missing.append(pip); report(False, f"套件 {pip}", "未安裝")
    if sys.platform != "win32": return finish(a, None)

    # 3. 圖檔格式 → 決定 CAD 最低版本（未給 --sample 時以 2018 格式為準）
    need = DWG_FMT["AC1032"]
    if a.sample:
        fmts = {}
        for f in glob.glob(os.path.join(a.sample, "**", "*.dwg"), recursive=True):
            if f.endswith("_比對標示.dwg"): continue
            try: h = open(f, "rb").read(6).decode("ascii", "replace")
            except OSError: continue
            fmts[h] = fmts.get(h, 0) + 1
        if not fmts: report(False, "圖檔", f"{a.sample} 底下找不到 DWG")
        else:
            known = [DWG_FMT[h] for h in fmts if h in DWG_FMT]
            if known: need = max(known, key=lambda t: t[1])
            report(True, "圖檔格式", "、".join(f"{DWG_FMT[h][0]} 格式 {n} 張" for h, n in sorted(fmts.items()) if h in DWG_FMT) or "無可辨識格式")
            unknown = {h: n for h, n in fmts.items() if h not in DWG_FMT}
            if unknown:   # 無法辨識的檔頭只提醒，不擋流程；這些圖可能轉檔失敗，會在 Excel 標為需人工比對
                report(False, "未知格式", "、".join(f"{h!r} {n} 張" for h, n in unknown.items()) + "（可能轉檔失敗）", must=False)
    ac_min, bc_min = max(need[1], 19), max(need[2], 18)
    yr = lambda v: ACAD_YEAR.get(v, "?")

    # 4. CAD
    bc = reg_versions("BricscadApp.AcadApplication")
    ac = reg_versions("AutoCAD.Application")
    bc_ok = [v for v in bc if v[0] >= bc_min]
    ac_ok = [v for v in ac if v[0] >= ac_min]
    for ver, pid in bc: report(ver >= bc_min, "BricsCAD", f"V{ver}" + ("" if ver >= bc_min else f"（太舊，需 V{bc_min} 以上）"), must=False)
    for ver, pid in ac: report(ver >= ac_min, "AutoCAD", f"R{ver}（{yr(ver)}）" + ("" if ver >= ac_min else f"（太舊：{need[0]} 格式圖檔需 R{ac_min}（{yr(ac_min)}）以上）"), must=False)
    if has_lt() and not ac_ok:
        report(False, "AutoCAD LT", "LT 版沒有自動化介面（COM），無法用於本工具", must=False)
    if not bc and not ac:
        report(False, "CAD 軟體", "找不到 BricsCAD 或 AutoCAD 完整版")

    pick = None
    if a.engine in ("auto", "bricscad") and bc_ok: pick = ("bricscad", bc_ok[-1])
    elif a.engine in ("auto", "autocad") and ac_ok: pick = ("autocad", ac_ok[-1])
    if pick is None and (bc or ac):
        report(False, "可用 CAD", f"沒有能開 {need[0]} 格式圖檔的 {'CAD' if a.engine == 'auto' else a.engine}（BricsCAD V{bc_min}+ 或 AutoCAD R{ac_min}（{yr(ac_min)}）+）")
    cfg = None
    if pick:
        eng, (ver, progid) = pick
        cfg = dict(cadcom.ENGINES[eng], engine=eng, progid=progid, version=ver)
        report(True, "使用 CAD", f"{cfg['name']} {('V' if eng == 'bricscad' else 'R')}{ver}（{progid}）")

    # 5. 實際啟動 CAD
    if a.full and cfg and not missing:
        before = set(cadcom.cad_procs(cfg["exe"])); app = None; own = set()
        try:
            app = cadcom.new_app(cfg)
            own = {cadcom.app_pid(app)} - {None}
            report(True, "COM 自動化", f"{cfg['name']} {app.Version} 可由程式控制")
            doc = cadcom.call(app.Documents.Add)
            devs = list(doc.ActiveLayout.GetPlotDeviceNames())
            pc3 = cfg["pc3"] if cfg["pc3"] in devs else next((d for d in devs if "pdf" in d.lower() and d.lower().endswith(".pc3")), None)
            report(pc3 is not None, "PDF 印表機", pc3 or f"找不到 {cfg['pc3']}（PDF 無法輸出）")
            if pc3: cfg["pc3"] = pc3
            try:
                cfg["plotstyles_dir"] = app.Preferences.Files.PrinterStyleSheetPath.split(";")[0]
                report(os.path.isdir(cfg["plotstyles_dir"]), "出圖型式資料夾", cfg["plotstyles_dir"])
            except Exception as e:
                report(False, "出圖型式資料夾", f"讀取失敗：{e}")
            doc.Close(False)
        except Exception as e:
            report(False, "COM 自動化", f"無法啟動 {cfg['name']}：{e}")
        finally:
            if app: cadcom.quit_app(app)
            cadcom.cleanup(cfg["exe"], before, own)
    elif cfg and not a.full:
        rows.append(("ℹ️", "完整檢查", "未加 --full：尚未實際啟動 CAD 驗證"))
    return finish(a, cfg, missing)

def finish(a, cfg, missing=()):
    w = max(len(r[1]) for r in rows) + 2
    for icon, item, detail in rows: print(f"{icon} {item.ljust(w)}{detail}")
    if missing: print(f"\n安裝缺少的套件：python -m pip install {' '.join(missing)}")
    if fatal:
        stale = os.path.join(a.work, "cad.json")
        if os.path.exists(stale): os.remove(stale)   # 避免後續步驟誤用上次的設定
        print(f"\n結果：❌ 環境未就緒（{ '、'.join(fatal) }）"); sys.exit(1)
    cadcom.save_cfg(a.work, cfg)
    print(f"\n結果：✅ 可以開始比對（設定已存到 {os.path.join(a.work, 'cad.json')}）")

if __name__ == "__main__":
    main()
