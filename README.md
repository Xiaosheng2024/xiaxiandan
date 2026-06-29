# EHX 下线防错程序

当前阶段已完成基于客户 Excel 模板的 A5 横向下线单 PDF 生成模块。根目录模板
`报交下线单模板.xlsx` 始终只读，程序只在临时目录处理模板副本。

同时已提供可运行的 PySide6 全屏扫码程序，包含 SQLite 追溯、物料动态导入、
重复/混料/格式防错、满箱生成 PDF、自动打印、失败恢复、历史查询和补打入口。

## 正式部署架构

### Windows 现场

1. 程序使用 ReportLab 编码规则和 Pillow 生成 Code128 PNG，不依赖条码字体。
2. openpyxl 将 PNG 嵌入 Excel 模板副本，保留合并单元格、打印区域、页边距和
   A5 横向设置。
3. Microsoft Excel COM 使用 `ExportAsFixedFormat` 导出 PDF 留档。
4. Microsoft Excel COM 使用 `PrintOut` 直接打印同名 XLSX。
5. Excel COM 失败时可用 ReportLab fallback 生成简化 PDF；失败数据和文件保留，
   可从历史记录补打。

### macOS 开发环境

macOS 只用于代码开发和逻辑验证，直接使用 ReportLab fallback。Mac 不验收正式
Excel 模板转换效果和真实打印效果。

Windows 才是正式 Excel 模板、打印区域、A5 横向和物理打印验收环境。

## 安装

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Windows 正式环境只要求已安装 Microsoft Excel、Python 依赖和打印机驱动，不要求
安装 LibreOffice、SumatraPDF 或 Code128 字体。

## config.json

```json
{
  "printer_name": "",
  "template_path": "报交下线单模板.xlsx",
  "output_pdf_dir": "output/pdf",
  "database_path": "data/ehx_guard.db",
  "reserved1_sub": "2918",
  "box_scan_count": 44,
  "line_name": "EHX",
  "station_name": "下线工位",
  "material_excel_path": "EHX物料号匹配.xlsx",
  "mii_enabled": false,
  "mii_base_url": "",
  "mii_token": "",
  "barcode_mode": "image",
  "barcode_show_text": true,
  "barcode_output_dir": "output/barcodes",
  "pdf_renderer": "excel_com",
  "print_method": "excel_com",
  "debug_no_print_on_mac": true,
  "mac_pdf_renderer": "reportlab",
  "windows_pdf_renderer": "excel_com",
  "windows_print_method": "excel_com"
}
```

`reserved1_sub` 对应模板占位符 `$Reserved1Sub$`，含义是公司名字代码，默认固定
为 `2918`。它与物料条码无关，不会改变 `5664620-CLBK06` 等物料前缀。客户后续
变更公司代码时，只需修改 `config.json`。

`printer_name` 为空时使用 Windows 默认打印机。

指定打印机时，必须填写 Windows 打印机列表中的完整名称，例如：

```json
"printer_name": "HP LaserJet MFP M132snw"
```

可在 Windows PowerShell 中查询完整名称：

```powershell
Get-Printer | Select-Object Name
```

正式打印由 Excel COM 调用工作表 `PrintOut`：

- `printer_name` 为空：`worksheet.PrintOut()`
- `printer_name` 非空：`worksheet.PrintOut(ActivePrinter=printer_name)`

如果指定打印机不存在或打印失败，PDF、同名 XLSX 和数据库记录都会保留，订单状态
记为 `PRINT_FAILED`，界面弹出失败原因，可在历史记录中补打。

默认 `barcode_mode=image`。程序生成并嵌入 PNG，`barcode_show_text` 控制条码图片
下方是否显示明文。旧模板字体方式仅作为兼容备用，可配置为
`"barcode_mode": "font"`。

默认 `pdf_renderer=excel_com`、`print_method=excel_com`。生成 PDF 时会在同一目录
保留同名 XLSX，打印时 Excel COM 直接打开该模板副本并执行 `PrintOut`。

macOS 使用 `mac_pdf_renderer=reportlab` 且
`debug_no_print_on_mac=true`：满箱后生成 PDF、将订单记为 `PDF_ONLY`，界面显示
“PDF已生成，已跳过打印”，随后自动进入下一箱。macOS 不会调用 soffice、Excel
COM 或 Windows 打印。

`box_scan_count` 是每箱需要成功扫描的数量。物料号不写死在程序中，首次启动时
从 `material_excel_path` 导入 SQLite 的 `material_mapping` 表，后续也可以从
数据库维护。

### 物料 Excel 格式

`EHX物料号匹配.xlsx` 使用固定的 A/B/C/D 四列：

| 列 | 含义 | 示例 |
| --- | --- | --- |
| A | 物料条码前缀 | `5664620-CLBK06` |
| B | 物料名称 | `主驾座椅背板总成 极夜黑` |
| C | 客户物料号/SAP物料号 | `566462001FA2` |
| D | 每箱数量 | `44` |

D 列为空时使用 `config.json` 的 `box_scan_count`。D 列非数字、非整数或小于等于
0 时导入失败，并提示具体 Excel 行号。每箱数量在第一件扫码识别物料时写入当前
下线单，此后物料表数量变化不会修改历史订单。

新箱在首件扫码前显示 `0/--`；识别物料后立即切换为该物料的进度，例如
`1/44`。

程序启动时会同步一次 Excel。运行过程中修改 Excel 后，可点击主界面的
“物料查看 / 重新导入”，导入完成后会显示新增、更新和禁用数量；也可以重启程序
使修改生效。

`mii_enabled` 默认必须为 `false`。当前 `mii_client.py` 只记录日志，不发送任何
网络请求；取得客户接口后仅需在该文件中补充请求和鉴权。

## 启动扫码程序

```powershell
python main.py
```

程序启动后自动全屏。扫码枪按键盘输入方式工作，条码后的回车会立即触发校验。
`Esc` 或 `Ctrl+Q` 退出程序。

主界面显示：

- 当前物料号和物料名称
- 每箱需扫、已扫和剩余数量
- 当前下线单号
- 最近扫码和错误原因
- 历史查询、补打和失败重试入口
- 物料查看、每箱数量和重新导入入口

成功扫码记录使用 SQLite 部分唯一索引约束完整条码，失败尝试仍会保存，因此重复、
混料、未配置和格式错误均可追溯。

## 扫码格式

物料前缀从 Excel 或 `material_mapping` 表动态读取。当前单件条码规则为：

```text
物料前缀 + yyyyMMdd + 3位流水号
```

例如：

```text
5664620-CLBK0620260616001
```

公司代码 `2918` 只填入 `$Reserved1Sub$`，不会改变条码中的 `4620`。

## 本地逻辑测试

以下测试不调用 LibreOffice，也不执行真实打印：

```powershell
python -m unittest tests.test_scanner_service -v
```

测试覆盖正常满箱、重复、混料、未配置、格式错误、不足满箱、重启恢复、PDF失败
保箱、打印失败保留 PDF 和历史查询。

## 运行环境检查

```powershell
python scripts\check_runtime.py
```

诊断结果包括操作系统、Python、三类 PDF 依赖、模板访问权限、输出目录权限、
默认打印机、配置打印机是否存在，以及当前平台的推荐渲染顺序。

如配置文件不在默认位置：

```powershell
python scripts\check_runtime.py --config D:\EHX\config.json
```

## 生成 PDF

准备 JSON 数据后执行：

```powershell
python generate_a5_pdf.py order.json output\pdf\EHX20260629185500.pdf
```

完整字段说明参见 [A5_PDF说明.md](A5_PDF说明.md)。

## Windows 部署与验收步骤

1. 确认 Microsoft Excel 可以正常启动并打开模板。
2. 安装 Python 依赖，其中 Windows 必须安装 `pywin32`。
3. 安装打印机驱动并打印 Windows 测试页。
4. 修改 `config.json`，填写打印机名称。
5. 运行 `python scripts\check_runtime.py`，确认 Excel COM、pywin32、模板、
   PDF/条码输出目录、SQLite 和打印机检查通过。
6. 启动 EHX 下线防错程序。
7. 扫描一组正常、重复、混料和未配置条码，验证防错提示。
8. 扫满一箱，检查生成的 PDF 为单页 A5 横向且模板字段完整。
9. 检查 Excel COM 是否直接打印 XLSX，并用扫码枪验证纸面条码。
10. 模拟打印失败，确认 PDF 和数据库记录仍保留，再从历史记录执行补打。

额外检查：

- Windows 10/11 64 位，打印机驱动已安装且测试页正常。
- `printer_name` 留空表示默认打印机；填写时必须与 Windows 打印机完整名称一致。
- 程序对 `output/pdf`、`logs`、`data` 和临时目录具有写权限。
- LibreOffice、SumatraPDF、Code128 字体、7-Zip 和 AweSun 均不是程序运行依赖。

## SQLite

程序直接使用 Python SQLite 驱动，不依赖 Navicat 或任何外部数据库管理软件。
人工排查数据时可选装 DB Browser for SQLite，但生产程序不能依赖它运行。
