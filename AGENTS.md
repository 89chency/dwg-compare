# AGENTS.md — 給在這個 repo 裡工作的 AI 代理（Codex / Claude Code）

## 這是什麼
`dwg-compare` 是新舊 DWG 圖說比對的 Agent Skill。**使用流程寫在 `SKILL.md`**：要幫使用者比對圖說時，照 `SKILL.md` 做，第一步一定是環境檢查。

## 結構
- `SKILL.md`：使用流程（給代理）
- `scripts/`：Python 腳本；入口是 `env_check.py`（環境檢查）和 `run_all.py`（完整流程）
- `references/pitfalls.md`：已知地雷與對策
- `tests/`：回歸測試

## 修改程式時
- 修改後一定要跑測試，全部 PASS 才算完成：
  ```
  python tests/test_diffeng.py
  python tests/test_make_pairs.py
  ```
- CAD 相關程式（`cadcom.py`、`markeng.py`、`plotpdf.py`、`batch_dxf.py`）要同時相容 BricsCAD 和 AutoCAD 的 COM 介面；兩者的差異集中寫在 `cadcom.ENGINES`。
- 所有開啟 CAD 的動作都要透過 `cadcom.run_isolated()` 在子行程執行並設逾時（CAD 當掉時 COM 會永久卡住）；只結束本工具啟動的 CAD，不可影響使用者自己開的 CAD。
- 原始圖檔一律唯讀；標示只寫在 `_比對標示.dwg` 複本。
- 程式註解和使用者訊息用繁體中文。
