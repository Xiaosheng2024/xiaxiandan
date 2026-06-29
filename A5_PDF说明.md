# A5 下线单 PDF 生成

生成器只读原始 Excel 模板。每次生成时先在临时目录创建模板副本并替换占位符。
Windows 使用 Microsoft Excel COM 导出 PDF；macOS 仅使用 ReportLab fallback
进行开发验证。只有转换和尺寸校验全部成功后，PDF 才会原子写入目标路径。

默认条码模式为 `image`：程序生成 Code128 PNG 并嵌入模板副本，不依赖 Code128
字体。模板中的四个条码区域分别为：

| 内容 | 图片锚点 |
| --- | --- |
| 供应商物料号 | `A9` |
| 客户物料号 | `F3` |
| 数量 | `F8` |
| Batch / 下线单号 | `F10` |

## 模板字段

| 模板占位符 | 程序字段 |
| --- | --- |
| `$SupplierName$` | `supplier_name` |
| `$PartName$` | `material_name` |
| `$CustomerName$` | `customer_name` |
| `$CustomerPartNo$` | `customer_material_code` |
| `$UpdatedAt$` | `production_time` |
| `$Reserved1Sub$` | `reserved1_sub`（公司名字代码，默认 `2918`） |
| `$SapMaterialNo$` | `material_code` |
| `$BoxQty$` | `quantity` |
| `$OfflineLocation$` | `offline_location` |
| `$Batch$` | `offline_order_no` |

`reserved1_sub` 与物料条码无关。物料条码前缀仍从物料配置表或
`material_mapping` 表读取，不允许使用公司代码替换条码内容。

## Windows 依赖

1. Python 3.10 或更高版本。
2. 执行 `pip install -r requirements.txt`。
3. 安装 Microsoft Excel 和 `pywin32`。
4. 不需要安装 LibreOffice、SumatraPDF 或 Code128 字体。
5. Excel COM 不可用时，程序可使用 ReportLab fallback 生成简化 PDF。

## JSON 示例

```json
{
  "offline_order_no": "EHX20260629185500",
  "material_code": "5664620-CLBK06",
  "material_name": "主驾座椅背板总成 极夜黑",
  "customer_material_code": "566462001FA2",
  "quantity": 6,
  "production_time": "2026-06-29T18:55:00",
  "offline_location": "EHX-FG"
}
```

## 命令

```powershell
python generate_a5_pdf.py order.json output\pdf\EHX20260629185500.pdf
```

如 LibreOffice 不在默认位置：

```powershell
python generate_a5_pdf.py order.json output\pdf\order.pdf `
  --soffice "C:\Program Files\LibreOffice\program\soffice.exe"
```
