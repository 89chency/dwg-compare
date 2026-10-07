"""CAD 引擎抽象層：BricsCAD / AutoCAD（完整版 2018+）共用 COM（ActiveX）介面。

- 設定來自 <work>/cad.json（env_check.py 產生）
- new_app()：DispatchEx 開「獨立執行個體」，不碰使用者自己開著的 CAD
- call()：AutoCAD 忙碌時 COM 會回「被呼叫端拒絕」，自動重試
- run_isolated()：每張圖在子行程處理並設逾時；逾時或當掉只結束本次新開的 CAD 程序
"""
import csv, io, json, os, subprocess, sys, time

ENGINES = {
    "bricscad": {"progid": "BricscadApp.AcadApplication", "exe": "bricscad.exe", "pc3": "Print As PDF.pc3", "name": "BricsCAD"},
    "autocad":  {"progid": "AutoCAD.Application", "exe": "acad.exe", "pc3": "DWG To PDF.pc3", "name": "AutoCAD"},
}
LAYER = "REV-比對標示"
DXF_SAVE_TYPE = 61          # AcSaveAsType：2013 DXF（BricsCAD/AutoCAD 共通）
RETRY_HRESULTS = {-2147418111, -2147417846}  # 被呼叫端拒絕 / 伺服器忙碌（物件已斷線重試也無效，直接拋出）

def load_cfg(work):
    p = os.path.join(work, "cad.json")
    if not os.path.exists(p):
        sys.exit(f"找不到 {p}，請先執行 env_check.py --work \"{work}\"")
    return json.load(open(p, encoding="utf-8"))

def save_cfg(work, cfg):
    os.makedirs(work, exist_ok=True)
    json.dump(cfg, open(os.path.join(work, "cad.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

def call(fn, *args, tries=30, wait=1.0):
    """COM 呼叫遇到 CAD 忙碌時重試。"""
    import pywintypes
    for k in range(tries):
        try:
            return fn(*args)
        except pywintypes.com_error as e:
            if e.args[0] in RETRY_HRESULTS and k < tries - 1:
                time.sleep(wait); continue
            raise

def app_pid(app):
    """由 CAD 主視窗找出本次啟動的程序 PID（之後只結束這個程序，不碰使用者自己開的 CAD）。"""
    try:
        import win32process
        return win32process.GetWindowThreadProcessId(int(app.HWND))[1]
    except Exception:
        return None

def new_app(cfg):
    import win32com.client
    app = call(win32com.client.DispatchEx, cfg["progid"])
    try: app.Visible = True   # 部分版本隱藏時開檔會異常
    except Exception: pass
    pid, pidfile = app_pid(app), os.environ.get("DWGC_PIDFILE")
    if pid and pidfile:   # 子行程模式：把 PID 交給父行程，逾時或當掉時由父行程結束
        with open(pidfile, "a", encoding="utf-8") as f: f.write(f"{pid}\n")
    return app

def quit_app(app):
    try: app.Quit()
    except Exception: pass

def open_doc(app, path, read_only=True):
    doc = call(app.Documents.Open, os.path.normpath(path), read_only)
    time.sleep(1)
    return doc

def variant(*vals):
    import win32com.client, pythoncom
    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, list(vals))

# ---- 子行程隔離 -------------------------------------------------------------
CRASH_TITLES = ("崩潰", "crash", "錯誤報告", "error report")

def cad_procs(exe):
    """{pid: 視窗標題}"""
    r = subprocess.run(["tasklist", "/V", "/FI", f"IMAGENAME eq {exe}", "/FO", "CSV", "/NH"], capture_output=True, text=True, errors="replace")
    return {int(row[1]): row[-1] for row in csv.reader(io.StringIO(r.stdout)) if len(row) > 1 and row[1].isdigit()}

def kill_pids(pids):
    for pid in pids:
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)

def cleanup(exe, before, own):
    """結束本工具啟動的 CAD（own），以及執行期間新冒出、標題為崩潰報告的程序；
    使用者在執行期間自己開的 CAD（不在 own、標題正常）不會被動到。"""
    for _ in range(3):
        procs = cad_procs(exe)
        targets = {p for p in procs if p in own} | {p for p, t in procs.items()
                   if p not in before and any(k in t.lower() for k in CRASH_TITLES)}
        if not targets: return
        kill_pids(targets); time.sleep(3)

def run_isolated(cfg, args, timeout=600, retries=1):
    """以子行程執行 python <args>；回傳 (ok, 最後一行輸出或錯誤)。同一時間只能有一個比對流程在跑。"""
    import tempfile
    msg = ""
    for _ in range(retries + 1):
        before = set(cad_procs(cfg["exe"]))
        fd, pidfile = tempfile.mkstemp(prefix="dwgc_pid_"); os.close(fd)
        env = dict(os.environ, PYTHONIOENCODING="utf-8", DWGC_PIDFILE=pidfile)
        try:
            r = subprocess.run([sys.executable] + args, timeout=timeout, capture_output=True,
                               text=True, encoding="utf-8", errors="replace", env=env)
            ok = r.returncode == 0
            msg = (r.stdout.strip().splitlines() or [""])[-1] if ok else (r.stderr.strip().splitlines() or ["error"])[-1]
        except subprocess.TimeoutExpired:
            ok, msg = False, f"timeout {timeout}s"
        own = {int(x) for x in open(pidfile, encoding="utf-8").read().split() if x.isdigit()}
        os.remove(pidfile)
        cleanup(cfg["exe"], before, own)
        if ok: return True, msg
    return False, msg

def read_lines(path):
    return [l.rstrip("\n").split("|") for l in open(path, encoding="utf-8") if l.strip()]
