# dwg-compare — 新舊 DWG 圖說比對

> An Agent Skill for **Claude Code** and **OpenAI Codex** that compares two revisions of AutoCAD/BricsCAD drawing sets, marks every change on the new drawings in red, and produces an Excel change log plus black-and-red PDFs. Windows + BricsCAD or full AutoCAD required. (Docs in Traditional Chinese.)

給 AI 代理新版、舊版兩個圖說資料夾，它會自動配對所有 DWG、逐張比對，在**新圖複本**上用紅框＋紅字標出改了什麼，給工程人員核對數量、追加減帳、判斷設計變更用。

## 產出

| 成果 | 說明 |
|---|---|
| **Excel 比對表** | 總表：每張圖是有變更、相同、新增、或未完成；變更明細：雲線編號、舊文字 → 新文字 |
| **標示 DWG** | 新版原檔旁多一個 `<原檔名>_比對標示.dwg`，原檔不動；變更處為紅色雲線框＋紅字說明，新增或修改的物件本身也標成紅色 |
| **黑白紅 PDF** | 黑線黑字、只有變更處印紅色；配置頁出 A3，模型空間依變更位置分區出 A1 |

能抓到的變更：文字（規格、尺寸、編號）、線條、填充、圖塊、尺寸標註、配置頁增刪等。會自動排除的雜訊：圖框欄位（圖號、日期）、Revit 匯出時每次都換的圖塊名稱、填充邊界起點不同等。

## 需求

| 項目 | 需求 |
|---|---|
| 作業系統 | Windows（CAD 自動化只能在 Windows 原生環境執行，不能在 WSL） |
| CAD | **BricsCAD V18 以上**，或 **AutoCAD 完整版**（2018 格式圖檔需 AutoCAD 2018 以上；**AutoCAD LT 不支援**，沒有自動化介面） |
| Python | 3.9 以上 |
| 套件 | `python -m pip install ezdxf pywin32 openpyxl pymupdf` |
| AI 代理 | Claude Code，或 OpenAI Codex CLI |

不確定環境夠不夠？裝好之後叫代理做比對，它第一步就會跑環境檢查，缺什麼會列出來。

## 安裝

### Claude Code
```
git clone https://github.com/89chency/dwg-compare.git "%USERPROFILE%\.claude\skills\dwg-compare"
```

### Codex
```
git clone https://github.com/89chency/dwg-compare.git "%USERPROFILE%\.codex\skills\dwg-compare"
```
Codex 預設的沙箱會擋住開啟 CAD 的動作。執行時請核准它要跑的指令，或用 `codex --sandbox danger-full-access` 啟動。

### 兩個都要用
clone 一份到 Claude Code 的資料夾，再用目錄連結讓 Codex 共用，之後只要更新一次：
```
mklink /J "%USERPROFILE%\.codex\skills\dwg-compare" "%USERPROFILE%\.claude\skills\dwg-compare"
```

### 不用 git
到 [Releases](https://github.com/89chency/dwg-compare/releases) 下載 `dwg-compare.skill`（就是 zip 檔），解壓後把 `dwg-compare` 資料夾放到上面的 skills 路徑。

### 更新
```
cd "%USERPROFILE%\.claude\skills\dwg-compare" && git pull
```

## 使用

重開 Claude Code 或 Codex 之後，直接用自然語言說，例如：

> 幫我比對新舊圖說，舊版在 `D:\案子\施工圖v1`，新版在 `D:\案子\發包圖v3`，結果放 `D:\案子\比對`

代理會依序：
1. **環境檢查**：Python 套件、CAD 種類與版本、圖檔格式、PDF 印表機
2. **確認**：輸入、輸出資料夾，以及是否同意把出圖型式檔（CTB）裝進 CAD；不同意的話只出 Excel 和 DWG
3. **背景執行**：轉檔 → 比對 → 標示 → Excel → PDF；數十張圖約需數十分鐘
4. **抽查 PDF 並回報**：重點列出規格、尺寸、配筋這類會影響數量的變更

### 也可以手動執行
```
python scripts\env_check.py --work %TEMP%\dwg-compare\案名 --sample <新版資料夾> --full
python scripts\run_all.py --old <舊版資料夾> --new <新版資料夾> --out <輸出資料夾> --work %TEMP%\dwg-compare\案名 --install-ctb
```
- `--work`：放轉檔的中間檔，可能有數百 MB，請放暫存區
- `--install-ctb`：把出圖型式檔複製到 CAD 的出圖型式資料夾，PDF 需要用到；不想改動 CAD 設定的話，改用 `--no-pdf`
- `--from dxf|diff|color|mark|report|pdf`：中斷後從指定步驟續跑

## 運作方式
1. **配對**：先依相對路徑配對；資料夾改名時，用「唯一同名檔」配對
2. **轉檔**：用 CAD 唯讀開啟 DWG、另存 DXF，每張圖用獨立的 CAD 執行個體處理並設逾時，當掉也不會卡住整批
3. **比對**：用 [ezdxf](https://ezdxf.mozman.at/) 為每個物件建立簽章（種類＋幾何＋文字＋線型等），找出新增或刪除的物件，再依距離分群成一處處變更
4. **標示**：在新圖複本畫雲線框和說明文字，改用新圖沒用到的顏色，並產生「只有這個顏色印紅、其餘全黑」的出圖型式檔
5. **輸出**：Excel、PDF

## 限制
- 同一台電腦同一時間只能跑一個比對流程
- 判斷依據是物件的幾何和文字，不理解設計意圖；重點變更仍需工程人員確認
- 「新版資料夾沒有此圖」不等於刪除，常見是這次只發了改過的圖
- **AutoCAD 路徑尚未實機驗證**；開發時是在 BricsCAD V26 上跑完整流程。用 AutoCAD 的話，請先拿 2～3 張圖試跑，有問題歡迎開 Issue

## 開發
```
python tests\test_diffeng.py
python tests\test_make_pairs.py
```
修改程式前請看 [AGENTS.md](AGENTS.md)；已知地雷整理在 [references/pitfalls.md](references/pitfalls.md)。

## 授權
[MIT](LICENSE)
