# POS — Prevent Negative Stock Sales

## منع بيع المخزون السالب في نقاط البيع

---

## Overview / نظرة عامة

**English:**
This module prevents POS cashiers from selling products when the resulting on-hand quantity in the POS-linked warehouse would drop below zero. It provides real-time stock validation at three checkpoints (add to cart, quantity change, payment validation), a configurable manager override with PIN authentication, and a full audit trail for compliance.

**العربية:**
تمنع هذه الوحدة أمناء الصندوق في نقاط البيع من بيع المنتجات عندما تصبح الكمية الفعلية في المستودع المرتبط بنقطة البيع أقل من الصفر. توفر التحقق الفوري من المخزون عند ثلاث نقاط (إضافة للسلة، تغيير الكمية، التحقق عند الدفع)، مع إمكانية تجاوز المدير عبر رقم التعريف الشخصي، وسجل تدقيق كامل للامتثال.

### Business Value / القيمة التجارية

- Stops phantom inventory and negative valuation / منع المخزون الوهمي والتقييم السالب
- Prevents COGS distortion / منع تشوه تكلفة البضاعة المباعة
- Forces operational discipline (receive before sell) / فرض الانضباط التشغيلي
- Required by audit and IFRS-compliant clients / مطلوب للعملاء الملتزمين بمعايير IFRS

---

## Installation / التثبيت

1. Copy the `pos_prevent_negative_stock` folder into your Odoo 19 `addons` directory.
2. Restart the Odoo server.
3. Go to **Apps**, remove the "Apps" filter, search for "Prevent Negative Stock".
4. Click **Install**.

No additional Python or JS libraries are required.

---

## Configuration / الإعدادات

### Enable the Feature

1. Go to **Point of Sale > Configuration > Point of Sale**.
2. Select your POS configuration.
3. Navigate to the **Inventory** tab.
4. In the **Stock Control — Negative Stock Prevention** section:
   - Toggle **Prevent Negative Stock** ON.
   - Select the **Stock Check Mode**: On Hand, Available (default), or Forecasted.
   - Configure **Stock Refresh Interval** (default: 60 seconds).

### Manager Override

- Toggle **Allow Manager Override** to enable PIN-based override.
- Select the **Override Group** (defaults to POS Manager).
- Optionally enable **Require Override Reason** to mandate a text reason.

### Exclusions

- Add product categories to **Excluded Categories** (e.g., Services).
- Add specific products to **Excluded Products**.
- Toggle **Block Unstorable Products** to apply checks on consumables/services too.

---

## Override Workflow / سير عمل التجاوز

1. Cashier scans/adds a product with insufficient stock.
2. A popup appears showing the product name, available qty, requested qty, and deficit.
3. If override is enabled:
   - Cashier clicks **Manager Override**.
   - Manager enters their PIN.
   - Optionally enters a reason.
   - On success: order proceeds, override is logged on the order line.
4. If override is disabled: only **Cancel** is available.

---

## Reporting / التقارير

- **Menu:** Point of Sale > Reporting > Negative Stock Overrides
- **Views:** Tree (list) and Pivot
- **Filters:** Date, Product, Override Manager, POS Config
- **Group By:** Product, Override Manager, Month
- **Export:** XLSX export supported

---

## Offline Behavior / السلوك دون اتصال

When the POS is offline:
- The last loaded stock snapshot is used for validation.
- An optional safety buffer percentage (`pos_negative_stock.offline_buffer_pct` system parameter) can reduce available qty to account for concurrent sales.
- When the POS reconnects, the server re-validates all orders. Unauthorized negative-stock orders are rejected.

---

## Limitations & Edge Cases / القيود والحالات الخاصة

- Stock data may be stale between refresh intervals; the server-side check is the authoritative gate.
- Unit-of-measure conversions depend on Odoo's standard UoM handling on the product model.
- Combo/bundle products are validated per component if individual products are in the order lines.
- Returns (negative qty lines) are never blocked.

---

## Compatibility / التوافق

| Requirement | Supported |
|---|---|
| Odoo 19 Community | Yes |
| Odoo 19 Enterprise | Yes |
| Multi-Company | Yes |
| Multi-Warehouse | Yes |
| RTL (Arabic) | Yes |

---

## Changelog / سجل التغييرات

### 19.0.1.0.0
- Initial release
- Core negative stock prevention with three checkpoints
- Manager PIN override with audit logging
- Configurable stock modes (on-hand, available, forecasted)
- Product and category exclusions
- Background stock refresh
- Server-side enforcement
- Arabic and English translations
- Override reporting (tree + pivot)

---

## Support / الدعم

**Author:** Mostafa — Odoo Functional Consultant

For support, feature requests, or bug reports, please contact the author directly.
