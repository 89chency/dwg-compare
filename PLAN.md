# PLAN — dwg-compare（新舊 DWG 圖說比對 skill）

## 目標
給新、舊兩個圖說資料夾，自動比對所有 DWG，在**新圖複本**上用紅框＋紅字標出差異，產出：
1. Excel 比對表（總表＋變更明細：舊文字 → 新文字）
2. 標示 DWG（`<原檔名>_比對標示.dwg`，存在新圖原檔旁，xref 才接得上；原檔不動）
3. 黑白紅 PDF（黑線黑字、變更處紅色；配置頁 A3、模型空間依變更位置分區出 A1）

來源：某統包工程案（2026-10）實作，經多輪程式審查修正後一般化。

## 需求（已和使用者確認）
- 通用：任何案子，依「相對路徑」配對，找不到時以唯一同名檔配對
- 要分享給同事：GitHub repo（89chency/dwg-compare）＋ .skill 檔
- 支援 CAD：BricsCAD、AutoCAD 完整版 2018 以上（AutoCAD LT 沒有 COM，不支援）
- **第一步一定是環境檢查**：Windows、Python 套件、CAD 種類與版本、PDF 印表機、出圖型式資料夾、圖檔格式能否開啟
- 不跑 skill-creator 評測（使用者決定）；只做單元測試＋語法檢查＋本機環境檢查

## 架構
```
dwg-compare/
├── SKILL.md                 流程說明（給 Claude）
├── README.md                安裝說明（給人）
├── PLAN.md
├── references/pitfalls.md   已知地雷與對策
├── scripts/
│   ├── env_check.py         環境檢查 → 寫 <work>/cad.json
│   ├── cadcom.py            CAD 引擎抽象（BricsCAD/AutoCAD）、COM 重試、子行程隔離
│   ├── run_all.py           總流程，可從任一步驟續跑
│   ├── make_pairs.py        新舊配對（相對路徑 → 唯一同名）、刪除圖說清單
│   ├── batch_dxf.py         DWG→DXF（指紋快取、逾時）
│   ├── pick_color.py        找新圖未使用的 ACI 當標示色，產生對應 CTB
│   ├── diffeng.py           ezdxf 實體簽章比對、分群
│   ├── markeng.py           在新圖複本畫雲線／紅字，變更物件改標示色
│   ├── plotpdf.py           黑白紅 PDF
│   └── report.py            Excel
└── tests/test_diffeng.py
```

## 和初版（單一案件版）的差異
| 項目 | 初版 | skill 版 |
|---|---|---|
| 路徑 | 寫死 | `--old --new --out --work` 參數 |
| CAD | 只有 BricsCAD | BricsCAD / AutoCAD 2018+（`cad.json` 決定） |
| 標示色 | 固定 ACI 16 | 掃描新圖挑未用色，CTB 動態產生 |
| CTB | 複製 monochrome.ctb 改 | ezdxf 從零產生 |
| 流程 | bash | `run_all.py`（Windows 不需 bash） |
| 刪除的圖 | 未列 | 舊版有、新版無 → 列入 Excel |
| AutoCAD 忙碌 | — | COM 呼叫遇「被呼叫端拒絕」自動重試 |

## 步驟與進度
- [x] 1. scripts 一般化（cadcom / env_check / make_pairs / pick_color / run_all）
- [x] 2. diffeng / markeng / plotpdf / report / batch_dxf 改參數化
- [x] 3. SKILL.md / README.md / references/pitfalls.md
- [x] 4. 單元測試、語法檢查、本機 env_check（BricsCAD 應通過、AutoCAD 2016 應判定不支援）
- [x] 5. git init → GitHub 私有 repo → 打包 .skill
- [x] 6. 程式審查（/code-review 8 項：配對重複、未知格式、STB 出圖、單張失敗中斷、xref 撞色、誤關使用者 CAD、重複讀檔、斷線重試）已修正

## 驗收
- `python tests/test_diffeng.py` 全部 PASS
- `env_check.py` 在本機：BricsCAD V26 → 可用；AutoCAD 2016 → 明確顯示「版本不足（需 2018+）」
- 所有 scripts 可 import、無語法錯誤
- 已知限制：AutoCAD 路徑未在實機跑過（本機僅 2016）
