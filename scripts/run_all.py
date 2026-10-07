"""新舊 DWG 圖說比對：完整流程（可從任一步驟續跑）。
前提：已執行 env_check.py --work <work> --full 且通過（產生 <work>/cad.json）。

步驟：pairs 配對 → dxf 轉檔 → diff 比對 → color 挑標示色/CTB → mark 標示 → report Excel → pdf 出圖
用法:
  python run_all.py --old <舊版資料夾> --new <新版資料夾> --out <輸出資料夾> --work <工作資料夾>
                    [--from pairs|dxf|diff|color|mark|report|pdf] [--install-ctb] [--no-pdf]
  --install-ctb：把產生的 CTB 複製到 CAD 的出圖型式資料夾（PDF 需要；會改動 CAD 設定資料夾，須先取得使用者同意）
輸出：<out>/新舊圖說比對清單.xlsx、<out>/PDF/、<out>/REV_mono_red<ACI>.ctb；標示 DWG 在新版原檔旁（<名>_比對標示.dwg）
"""
import argparse, glob, os, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cadcom

STEPS = ["pairs", "dxf", "diff", "color", "mark", "report", "pdf"]

def py(script, *args):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, os.path.join(HERE, script), *args], env=env)
    if r.returncode != 0: sys.exit(f"步驟 {script} 失敗（結束碼 {r.returncode}）")

def step(name):
    print(f"\n===== {name}  {time.strftime('%H:%M:%S')} =====", flush=True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", required=True); ap.add_argument("--new", required=True)
    ap.add_argument("--out", required=True); ap.add_argument("--work", required=True)
    ap.add_argument("--from", dest="start", default="pairs", choices=STEPS)
    ap.add_argument("--install-ctb", action="store_true"); ap.add_argument("--no-pdf", action="store_true")
    a = ap.parse_args()
    cfg = cadcom.load_cfg(a.work)
    todo = STEPS[STEPS.index(a.start):]
    res = os.path.join(a.work, "res")

    if "pairs" in todo:
        step("配對"); py("make_pairs.py", "--old", a.old, "--new", a.new, "--work", a.work)
    pairs = cadcom.read_lines(os.path.join(a.work, "pairs.txt"))
    ids = [f"{i:02d}" for i in range(len(pairs))]

    if "dxf" in todo:
        step(f"轉檔（{len(pairs)} 組，每張約 5～60 秒）"); py("batch_dxf.py", "--work", a.work)
    if "diff" in todo:
        step("比對")
        for f in glob.glob(os.path.join(res, "*.json")): os.remove(f)   # 清掉上一輪結果，避免混用
        ok = [i for i in ids if all(os.path.exists(os.path.join(a.work, "dxf", f"{i}_{t}.dxf")) for t in ("old", "new"))]
        for i in sorted(set(ids) - set(ok)): print(f"{i} 轉檔未成功，略過（Excel 會標示需人工比對）")
        if ok: py("diffeng.py", "--work", a.work, *ok)
    if "color" in todo:
        step("挑標示色"); py("pick_color.py", "--work", a.work, "--out", a.out)
        cfg = cadcom.load_cfg(a.work)
        if not a.no_pdf:
            dst = cfg.get("plotstyles_dir")
            if not dst:
                print("⚠️ cad.json 沒有出圖型式資料夾（env_check 未加 --full），PDF 會略過")
            elif not os.path.exists(os.path.join(dst, cfg["ctb"])):
                if a.install_ctb:
                    shutil.copy2(os.path.join(a.out, cfg["ctb"]), dst); print(f"已安裝 {cfg['ctb']} → {dst}")
                else:
                    print(f"⚠️ {cfg['ctb']} 不在 {dst}；未加 --install-ctb，PDF 會略過")
    if "mark" in todo:
        done = [i for i in ids if os.path.exists(os.path.join(res, f"{i}.json"))]
        step(f"標示（{len(done)} 張）")
        for f in glob.glob(os.path.join(res, "*_marked.json")): os.remove(f)
        if done: py("markeng.py", "--work", a.work, *done)
    if "report" in todo:
        step("Excel"); py("report.py", "--work", a.work, "--xlsx", os.path.join(a.out, "新舊圖說比對清單.xlsx"))
    if "pdf" in todo and not a.no_pdf:
        cfg = cadcom.load_cfg(a.work); dst = cfg.get("plotstyles_dir")
        if dst and cfg.get("ctb") and os.path.exists(os.path.join(dst, cfg["ctb"])):
            items = sorted(glob.glob(os.path.join(res, "*_marked.json")))
            step(f"PDF（{len(items)} 份）"); py("plotpdf.py", "--work", a.work, "--out", os.path.join(a.out, "PDF"), *items)
        else:
            print("PDF 略過：出圖型式（CTB）尚未安裝到 CAD")
    print(f"\n完成 {time.strftime('%H:%M:%S')}，輸出：{a.out}")

if __name__ == "__main__":
    main()
