"""新舊圖檔配對（所有流程共用的索引來源）。
配對規則：新版每個 DWG 先找舊版「相同相對路徑」；找不到時，舊版若剛好只有一個同名檔就用它。
輸出（<work>/）：
  pairs_all.txt  專業|舊檔(可能不存在)|新檔      ← 新版所有 DWG
  pairs.txt      專業|舊檔|新檔                  ← 兩版都有且內容不同 → 轉檔/比對/標示的索引（順序固定）
  removed.txt    專業|舊檔                       ← 舊版有、新版沒有
「專業」取新版資料夾下第一層子資料夾名稱（例：1.建築、2.結構）。
用法: python make_pairs.py --old <舊版資料夾> --new <新版資料夾> --work <工作資料夾>
"""
import argparse, collections, filecmp, glob, os

MARK_SUFFIX = "_比對標示.dwg"

def dwgs(root):
    return sorted(p.replace("\\", "/") for p in glob.glob(os.path.join(root, "**", "*.dwg"), recursive=True)
                  if not p.endswith(MARK_SUFFIX))

def kind_of(path, root):
    rel = os.path.relpath(path, root).replace("\\", "/")
    return rel.split("/")[0] if "/" in rel else "（根目錄）"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", required=True); ap.add_argument("--new", required=True); ap.add_argument("--work", required=True)
    a = ap.parse_args()
    old_root, new_root = os.path.abspath(a.old), os.path.abspath(a.new)
    olds, news = dwgs(old_root), dwgs(new_root)
    by_name = collections.defaultdict(list)
    for o in olds: by_name[os.path.basename(o).lower()].append(o)
    # 第一輪：相對路徑完全相同者先配；第二輪才對剩下的用「唯一同名檔」配，避免一張舊圖被配給兩張新圖
    match = {}
    for n in news:
        o = os.path.join(old_root, os.path.relpath(n, new_root)).replace("\\", "/")
        if os.path.exists(o): match[n] = o
    used = set(match.values())
    for n in news:
        if n in match: continue
        cand = [c for c in by_name[os.path.basename(n).lower()] if c not in used]
        if len(cand) == 1: match[n] = cand[0]; used.add(cand[0])
    rows = [(kind_of(n, new_root), match.get(n) or os.path.join(old_root, os.path.relpath(n, new_root)).replace("\\", "/"), n)
            for n in news]
    os.makedirs(a.work, exist_ok=True)
    w = lambda name: open(os.path.join(a.work, name), "w", encoding="utf-8", newline="\n")
    n_diff = 0
    with w("pairs_all.txt") as fa, w("pairs.txt") as fp:
        for k, o, n in rows:
            fa.write(f"{k}|{o}|{n}\n")
            if os.path.exists(o) and not filecmp.cmp(o, n, shallow=False):
                fp.write(f"{k}|{o}|{n}\n"); n_diff += 1
    removed = [o for o in olds if o not in used]
    with w("removed.txt") as fr:
        for o in removed: fr.write(f"{kind_of(o, old_root)}|{o}\n")
    json_meta = os.path.join(a.work, "roots.txt")
    open(json_meta, "w", encoding="utf-8").write(f"{old_root}\n{new_root}\n")
    n_same = sum(1 for k, o, n in rows if os.path.exists(o)) - n_diff
    print(f"新版 {len(news)} 張：有變動 {n_diff}、相同 {n_same}、新增 {len(news) - n_diff - n_same}；舊版獨有（刪除）{len(removed)}")

if __name__ == "__main__":
    main()
