# EHX 下线防错程序

当前阶段已完成基于客户 Excel 模板的 A5 横向下线单 PDF 生成模块。原始模板
`Wologic/System/报交下线单模板.xlsx` 始终只读，程序只在临时目录处理模板副本。

同时已提供可运行的 PySide6 全屏扫码程序，包含 SQLite 追溯、物料动态导入、
重复/混料/格式防错、满箱生成 PDF、自动打印、失败恢复、历史查询和补打入口。

## 正式部署架构

### Windows 现场

1. LibreOffice headless：使用 Excel 模板副本转换 PDF，保留合并单元格、字体、
   Code 128 字体、打印区域、A5 横向和分页设置。
2. ReportLab fallback：LibreOffice 不可用或转换失败时生成简化的单页 A5 PDF，包含
   完整字段和可扫描的 Code 128 条码。
3. SumatraPDF：将生成成功的 PDF 静默发送到配置打印机；打印失败保留 PDF 和业务
   数据，供历史记录补打。

### macOS 开发环境

macOS 只用于代码开发和逻辑验证，默认完全跳过 soffice，直接使用 ReportLab
fallback。Mac 不验收正式 Excel 模板转换效果和真实打印效果。只有在
`config.json` 明确设置 `"enable_office_pdf_on_mac": true` 时才允许调用 soffice。

Windows 才是正式 PDF 版式、Code128 字体、打印区域、A5 横向和物理打印验收环境。

## 安装

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Windows 正式环境安装 LibreOffice、SumatraPDF 和 Code128 字体。ReportLab fallback
使用程序内置条码绘制，不依赖 Code128 字体。

## config.json

```json
{
  "printer_name": "",
  "libreoffice_path": "",
  "sumatra_path": "",
  "template_path": "Wologic/System/报交下线单模板.xlsx",
  "output_pdf_dir": "output/pdf",
  "database_path": "data/ehx_guard.db",
  "enable_office_pdf_on_mac": false,
  "reserved1_sub": "2918",
  "box_scan_count": 6,
  "line_name": "EHX",
  "station_name": "下线工位",
  "material_excel_path": "EHX物料号匹配.xlsx",
  "mii_enabled": false,
  "mii_base_url": "",
  "mii_token": ""
}
```

`reserved1_sub` 对应模板占位符 `$Reserved1Sub$`，含义是公司名字代码，默认固定
为 `2918`。它与物料条码无关，不会改变 `5664620-CLBK06` 等物料前缀。客户后续
变更公司代码时，只需修改 `config.json`。

`libreoffice_path` 和 `sumatra_path` 为空时自动检查：

- `C:\Program Files\LibreOffice\program\soffice.exe`
- `C:\Program Files (x86)\LibreOffice\program\soffice.exe`
- `C:\Program Files\SumatraPDF\SumatraPDF.exe`
- `C:\Program Files (x86)\SumatraPDF\SumatraPDF.exe`

`printer_name` 为空时使用 Windows 默认打印机。

`box_scan_count` 是每箱需要成功扫描的数量。物料号不写死在程序中，首次启动时
从 `material_excel_path` 导入 SQLite 的 `material_mapping` 表，后续也可以从
数据库维护。

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

1. 安装 Code128 条形码字体，注销或重启 Windows 后确认字体已注册。
2. 安装 `LibreOffice_25.8.4_Win_x86-64.msi`。
3. 安装 `SumatraPDF-3.5.2-64-install.exe`。
4. 修改 `config.json`，填写打印机名称；非默认安装路径时填写两个程序路径。
5. 运行 `python scripts\check_runtime.py`，确认模板、字体、PDF、日志、SQLite、
   LibreOffice、SumatraPDF 和打印机检查通过。
6. 启动 EHX 下线防错程序。
7. 扫描一组正常、重复、混料和未配置条码，验证防错提示。
8. 扫满一箱，检查生成的 PDF 为单页 A5 横向且模板字段完整。
9. 检查 SumatraPDF 是否自动静默打印，并用扫码枪验证纸面条码。
10. 模拟打印失败，确认 PDF 和数据库记录仍保留，再从历史记录执行补打。

额外检查：

- Windows 10/11 64 位，打印机驱动已安装且测试页正常。
- `printer_name` 必须与 Windows 打印机列表中的名称完全一致。
- 程序对 `output/pdf`、`logs`、`data` 和临时目录具有写权限。
- 7-Zip 和 AweSun 可以作为安装、维护工具，但不是程序运行依赖。

## SQLite

程序直接使用 Python SQLite 驱动，不依赖 Navicat 或任何外部数据库管理软件。
人工排查数据时可选装 DB Browser for SQLite，但生产程序不能依赖它运行。
