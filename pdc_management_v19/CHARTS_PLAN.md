# Phase 5.3 — Chart Widgets Research & Plan  ✅ IMPLEMENTED

> **Status:** Complete — all three widgets implemented and approved in Phase 5.3.
> See `static/src/js/pdc_dashboard_widgets.js` and `static/src/xml/pdc_dashboard_widgets.xml`.

## 1. Chart.js in Odoo 19 — Confirmed Facts

### Bundle location
```
web/static/lib/Chart/Chart.js
```
Registered as asset bundle key: `web.chartjs_lib`

### How to load (MUST use async bundle load)
```javascript
import { loadBundle } from "@web/core/assets";

setup() {
    onWillStart(async () => await loadBundle("web.chartjs_lib"));
}
```
After `loadBundle` resolves, `Chart` is available as a **global** (window.Chart).
No `import Chart from ...` needed — it is NOT an ES module.

### Reference implementation (Odoo 19 built-in)
File: `web/static/src/views/fields/journal_dashboard_graph/journal_dashboard_graph_field.js`

Key patterns extracted:
```javascript
import { loadBundle } from "@web/core/assets";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "../standard_field_props";
import { Component, onWillStart, useEffect, useRef } from "@odoo/owl";

class MyChartWidget extends Component {
    static template = "my_module.MyChartTemplate";
    static props = { ...standardFieldProps };

    setup() {
        this.chart = null;
        this.canvasRef = useRef("canvas");
        onWillStart(async () => await loadBundle("web.chartjs_lib"));
        useEffect(() => {
            this.renderChart();
            return () => {
                if (this.chart) { this.chart.destroy(); }
            };
        });
    }

    renderChart() {
        if (this.chart) { this.chart.destroy(); }
        this.chart = new Chart(this.canvasRef.el, this.getConfig());
    }

    getConfig() { /* returns Chart.js config object */ }
}

registry.category("fields").add("my_widget_name", {
    component: MyChartWidget,
    supportedTypes: ["json"],   // <-- "json" for fields.Json
});
```

### Owl template (minimal)
```xml
<t t-name="pdc_management_v19.MyChartTemplate">
    <div style="position:relative; height:240px;">
        <canvas t-ref="canvas"/>
    </div>
</t>
```
Height must be set on the **container div**, not on the canvas.
Chart.js reads the container dimensions for `maintainAspectRatio: false`.

### Key difference vs journal_dashboard_graph
The built-in widget uses `fields.Text` containing a JSON *string*, so it
calls `JSON.parse(this.props.record.data[this.props.name])`.

Our `fields.Json` is already deserialized by Odoo's ORM before reaching the
client. No `JSON.parse()` needed:
```javascript
// For fields.Json — already a JS object:
const fieldValue = this.props.record.data[this.props.name] || { data: [] };
const items = fieldValue.data || [];
```

---

## 2. Widget Plan

### Shared data shape (from pdc_dashboard.py)
```
state_distribution_data  = { "data": [{"label": str, "value": int}, ...] }
top_partners_data        = { "data": [{"label": str, "value": float}, ...] }
monthly_cash_flow_data   = { "data": [{"month": str, "inflow": float, "outflow": float}, ...] }
bounce_reasons_data      = { "data": [{"label": str, "value": int}, ...] }
```

### Widget 1 — `pdc_pie_chart`
Used by: `state_distribution_data`
Chart type: `"doughnut"` (visually cleaner than pie for dashboards)
Data mapping: `items.map(i => i.value)` / `items.map(i => i.label)`
Colors: 10 fixed colors cycling through Odoo's color palette
Legend: right side, scrollable

### Widget 2 — `pdc_bar_chart`
Used by: `top_partners_data`, `bounce_reasons_data`
Chart type: `"bar"` (horizontal for partners, vertical for bounce reasons)
- Partners: horizontal bar (`indexAxis: 'y'`) — long partner names fit better
- Bounce reasons: vertical bar (default)
Since both use the same widget, distinguish by data length:
  - If items[0].label length > 15 chars → horizontal; otherwise vertical
Colors: single color (#875A7B — Odoo purple) with opacity variation

### Widget 3 — `pdc_line_chart`
Used by: `monthly_cash_flow_data`
Chart type: `"bar"` (grouped bars — better for comparing inflow vs outflow than lines)
Two datasets: inflow (green) and outflow (red), grouped per month
Legend: top
Tooltip: shows both values on hover

---

## 3. Assets Registration

Add to `__manifest__.py`:
```python
'assets': {
    'web.assets_backend': [
        'pdc_management_v19/static/src/js/pdc_dashboard_widgets.js',
        'pdc_management_v19/static/src/xml/pdc_dashboard_widgets.xml',
    ],
},
```

Files to create:
- `static/src/js/pdc_dashboard_widgets.js`
- `static/src/xml/pdc_dashboard_widgets.xml`

---

## 4. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Chart.js version mismatch | Use only Chart.js 3.x API (no v4 syntax) — Odoo 19 ships Chart.js 3.x |
| Canvas height collapse | Always set `style="height:Npx"` on wrapper div, use `maintainAspectRatio: false` |
| Data null/empty crash | Guard: `const items = (fieldValue && fieldValue.data) || []` |
| Widget not found error | Use `supportedTypes: ["json"]` — matches `fields.Json` |
| Dark mode colors | Optional: import `getColor` from `@web/core/colors/colors` for theme-aware colors |

---

## 5. Implementation Order

1. Create `static/src/` directory structure
2. Write `pdc_dashboard_widgets.xml` (Owl templates — just canvas containers)
3. Write `pdc_dashboard_widgets.js` (three widget classes + registry entries)
4. Update `__manifest__.py` assets
5. Restart Odoo (`--update pdc_management_v19`)
6. Test each chart with demo data
