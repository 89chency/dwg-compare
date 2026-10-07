"""回歸測試：配對規則（相對路徑優先，再用唯一同名檔；一張舊圖不可配給兩張新圖）。"""
import os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "scripts", "make_pairs.py")

def touch(path, data=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "wb").write(data)

root = tempfile.mkdtemp(prefix="dwgc_pairs_")
old, new, work = (os.path.join(root, d) for d in ("old", "new", "work"))
touch(f"{old}/B/X.dwg", b"old-x")          # 舊版只有 B/X
touch(f"{new}/A/X.dwg", b"new-ax")         # 新版 A/X：舊版沒有 A/ → 不可搶走 B/X
touch(f"{new}/B/X.dwg", b"new-bx")         # 新版 B/X：相對路徑完全相同 → 應配到 B/X
touch(f"{old}/arch/Y.dwg", b"y1")          # 資料夾改名：arch → 1.建築，唯一同名 → 應配上
touch(f"{new}/1.建築/Y.dwg", b"y2")
touch(f"{old}/only/Z.dwg", b"z")           # 舊版獨有
subprocess.run([sys.executable, SCRIPT, "--old", old, "--new", new, "--work", work], check=True, capture_output=True)

rows = {n.replace("\\", "/").split("/new/")[1]: o for _, o, n in
        (l.rstrip("\n").split("|") for l in open(f"{work}/pairs_all.txt", encoding="utf-8"))}
olds = [o for o in rows.values() if os.path.exists(o)]
checks = {
    "B/X 以相對路徑配對": rows["B/X.dwg"].endswith("old/B/X.dwg"),
    "A/X 不可搶走 B/X": not os.path.exists(rows["A/X.dwg"]),
    "改名資料夾以唯一同名檔配對": rows["1.建築/Y.dwg"].endswith("old/arch/Y.dwg"),
    "一張舊圖只配一次": len(olds) == len(set(olds)),
    "舊版獨有列入 removed": "only/Z.dwg" in open(f"{work}/removed.txt", encoding="utf-8").read(),
}
for k, v in checks.items(): print(f"{k:16s} {'PASS' if v else 'FAIL'}")
ok = all(checks.values()); print("ALL PASS" if ok else "SOME FAIL"); sys.exit(0 if ok else 1)
