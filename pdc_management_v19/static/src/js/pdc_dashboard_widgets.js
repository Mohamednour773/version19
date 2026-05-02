/** @odoo-module **/

/**
 * PDC Dashboard Chart Widgets  (Phase 5.3)
 *
 * Three Owl 3.0 field widgets that render Chart.js charts from fields.Json data:
 *   pdc_pie_chart  – doughnut chart for check state distribution
 *   pdc_bar_chart  – horizontal bar chart for top partners / bounce reasons
 *   pdc_line_chart – filled line chart for monthly cash flow (inflow vs outflow)
 *
 * Chart.js is loaded on-demand via Odoo's asset bundle mechanism:
 *   await loadBundle("web.chartjs_lib")
 * After that, `Chart` is available as a window global (not an ES module).
 *
 * Data shape expected from pdc.dashboard computed fields (fields.Json):
 *   state_distribution_data  → { data: [{label, value}, ...] }
 *   top_partners_data        → { data: [{label, value}, ...] }
 *   bounce_reasons_data      → { data: [{label, value}, ...] }
 *   monthly_cash_flow_data   → { data: [{month, inflow, outflow}, ...] }
 */

import { loadBundle }       from "@web/core/assets";
import { registry }         from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, onWillStart, useEffect, useRef, useState } from "@odoo/owl";

// ── Colour palettes ─────────────────────────────────────────────────────────

/** One colour per state bucket (10 states defined in pdc_dashboard.py).
 *  Colours are chosen to roughly match the semantic state colours used in
 *  the KPI cards: green = good, red = problem, blue = in-progress, grey = neutral.
 */
const PIE_COLORS = [
    "#1976D2",   // registered        – blue
    "#0097A7",   // under_collection  – teal
    "#388E3C",   // cleared           – dark green
    "#D32F2F",   // bounced           – red
    "#7B1FA2",   // settled           – purple
    "#F57C00",   // printed           – amber
    "#00796B",   // delivered         – dark teal
    "#303F9F",   // paid              – indigo
    "#757575",   // cancelled         – grey
    "#5D4037",   // returned          – brown
];

const INFLOW_BORDER  = "rgba(46, 125, 50, 0.9)";   // dark green line
const INFLOW_FILL    = "rgba(46, 125, 50, 0.10)";   // dark green fill
const OUTFLOW_BORDER = "rgba(183, 28, 28, 0.9)";    // dark red line
const OUTFLOW_FILL   = "rgba(183, 28, 28, 0.08)";   // dark red fill

// ── Utility ─────────────────────────────────────────────────────────────────

/**
 * Safely extract the `data` array from the JSON field value.
 * Handles null / undefined / missing-key gracefully.
 */
function getItems(props) {
    const raw = props.record.data[props.name];
    return (raw && Array.isArray(raw.data)) ? raw.data : [];
}

// ═══════════════════════════════════════════════════════════════════════════
// 1.  pdc_pie_chart  —  state distribution (doughnut)
// ═══════════════════════════════════════════════════════════════════════════

class PDCPieChart extends Component {
    static template = "pdc_management_v19.PDCPieChart";
    static props    = { ...standardFieldProps };

    setup() {
        this.chart     = null;
        this.canvasRef = useRef("canvas");
        this.state     = useState({ hasData: false });

        // Load Chart.js before first render
        onWillStart(async () => await loadBundle("web.chartjs_lib"));

        // Re-render chart after every Owl render cycle.
        // cleanup() destroys the Chart.js instance to prevent memory leaks.
        useEffect(() => {
            const items = getItems(this.props);
            this.state.hasData = items.length > 0;
            this._renderChart(items);
            return () => this._destroyChart();
        });
    }

    _destroyChart() {
        if (this.chart) {
            this.chart.destroy();
            this.chart = null;
        }
    }

    _renderChart(items) {
        this._destroyChart();
        // Guard: nothing to render without data or a mounted canvas
        if (!items.length || !this.canvasRef.el) return;

        this.chart = new Chart(this.canvasRef.el, {
            type: "doughnut",
            data: {
                labels:   items.map((i) => i.label),
                datasets: [{
                    data:            items.map((i) => i.value),
                    backgroundColor: items.map((_, idx) =>
                        PIE_COLORS[idx % PIE_COLORS.length]
                    ),
                    borderWidth:  2,
                    borderColor:  "#fff",
                    hoverOffset:  8,
                }],
            },
            options: {
                responsive:          true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: "right",
                        labels: {
                            boxWidth:  12,
                            padding:   10,
                            font:      { size: 11 },
                            // Keep legend text LTR so items align correctly
                            textDirection: "ltr",
                        },
                    },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => {
                                const total = ctx.dataset.data.reduce(
                                    (s, v) => s + v, 0
                                );
                                const pct = total
                                    ? ((ctx.parsed / total) * 100).toFixed(1)
                                    : "0.0";
                                return `  ${ctx.label}: ${ctx.parsed}  (${pct}%)`;
                            },
                        },
                    },
                },
                // aria title for screen readers
                onHover: null,
            },
        });
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// 2.  pdc_bar_chart  —  top partners or bounce reasons (horizontal bar)
// ═══════════════════════════════════════════════════════════════════════════

class PDCBarChart extends Component {
    static template = "pdc_management_v19.PDCBarChart";
    static props    = { ...standardFieldProps };

    setup() {
        this.chart     = null;
        this.canvasRef = useRef("canvas");
        this.state     = useState({ hasData: false });

        onWillStart(async () => await loadBundle("web.chartjs_lib"));

        useEffect(() => {
            const items = getItems(this.props);
            this.state.hasData = items.length > 0;
            this._renderChart(items);
            return () => this._destroyChart();
        });
    }

    _destroyChart() {
        if (this.chart) {
            this.chart.destroy();
            this.chart = null;
        }
    }

    _renderChart(items) {
        this._destroyChart();
        if (!items.length || !this.canvasRef.el) return;

        // Build opacity-varied shades of Odoo purple (#875A7B) so top bar
        // is the most saturated and lower bars fade slightly.
        const total  = items.length;
        const colors = items.map((_, idx) => {
            const alpha = 0.95 - (idx / Math.max(total - 1, 1)) * 0.45;
            return `rgba(135, 90, 123, ${alpha.toFixed(2)})`;
        });

        this.chart = new Chart(this.canvasRef.el, {
            type: "bar",
            data: {
                labels:   items.map((i) => i.label),
                datasets: [{
                    data:            items.map((i) => i.value),
                    backgroundColor: colors,
                    borderWidth:     0,
                    borderRadius:    3,
                }],
            },
            options: {
                indexAxis:           "y",    // horizontal bars
                responsive:          true,
                maintainAspectRatio: false,
                plugins: {
                    legend:  { display: false },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => `  ${ctx.formattedValue}`,
                        },
                    },
                },
                scales: {
                    x: {
                        beginAtZero: true,
                        grid:  { color: "rgba(0, 0, 0, 0.05)" },
                        ticks: { font: { size: 10 } },
                    },
                    y: {
                        grid:  { display: false },
                        ticks: {
                            font:           { size: 11 },
                            // Truncate very long partner names in the axis
                            callback: (val, idx) => {
                                const lbl = items[idx] ? items[idx].label : String(val);
                                return lbl.length > 22
                                    ? lbl.substring(0, 20) + "…"
                                    : lbl;
                            },
                        },
                    },
                },
            },
        });
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// 3.  pdc_line_chart  —  monthly cash flow (filled area, 2 datasets)
// ═══════════════════════════════════════════════════════════════════════════

class PDCLineChart extends Component {
    static template = "pdc_management_v19.PDCLineChart";
    static props    = { ...standardFieldProps };

    setup() {
        this.chart     = null;
        this.canvasRef = useRef("canvas");
        this.state     = useState({ hasData: false });

        onWillStart(async () => await loadBundle("web.chartjs_lib"));

        useEffect(() => {
            const items = getItems(this.props);
            // Only flag as "has data" when at least one non-zero value exists
            this.state.hasData = items.some((i) => i.inflow || i.outflow);
            this._renderChart(items);
            return () => this._destroyChart();
        });
    }

    _destroyChart() {
        if (this.chart) {
            this.chart.destroy();
            this.chart = null;
        }
    }

    /** Format large numbers for the Y-axis tick labels (1 000 → 1K, etc.) */
    _fmtTick(v) {
        if (Math.abs(v) >= 1_000_000) return (v / 1_000_000).toFixed(1) + "M";
        if (Math.abs(v) >= 1_000)     return (v / 1_000).toFixed(0) + "K";
        return String(v);
    }

    _renderChart(items) {
        this._destroyChart();
        if (!items.length || !this.canvasRef.el) return;

        const fmtTick = this._fmtTick.bind(this);

        this.chart = new Chart(this.canvasRef.el, {
            type: "line",
            data: {
                labels:   items.map((i) => i.month),
                datasets: [
                    {
                        label:            "Inflow",
                        data:             items.map((i) => i.inflow),
                        borderColor:      INFLOW_BORDER,
                        backgroundColor:  INFLOW_FILL,
                        fill:             true,
                        tension:          0.35,
                        borderWidth:      2,
                        pointRadius:      4,
                        pointHoverRadius: 7,
                    },
                    {
                        label:            "Outflow",
                        data:             items.map((i) => i.outflow),
                        borderColor:      OUTFLOW_BORDER,
                        backgroundColor:  OUTFLOW_FILL,
                        fill:             true,
                        tension:          0.35,
                        borderWidth:      2,
                        pointRadius:      4,
                        pointHoverRadius: 7,
                    },
                ],
            },
            options: {
                responsive:          true,
                maintainAspectRatio: false,
                // Show both series' values in a single tooltip bubble
                interaction: { mode: "index", intersect: false },
                plugins: {
                    legend: {
                        position: "top",
                        labels:   {
                            boxWidth:  12,
                            padding:   14,
                            font:      { size: 11 },
                        },
                    },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => {
                                const v = ctx.parsed.y;
                                return `  ${ctx.dataset.label}: ${v.toLocaleString(
                                    undefined,
                                    { minimumFractionDigits: 2, maximumFractionDigits: 2 }
                                )}`;
                            },
                        },
                    },
                },
                scales: {
                    x: {
                        grid:  { display: false },
                        ticks: { font: { size: 11 } },
                    },
                    y: {
                        beginAtZero: true,
                        grid:        { color: "rgba(0, 0, 0, 0.05)" },
                        ticks: {
                            font:     { size: 10 },
                            callback: fmtTick,
                        },
                    },
                },
            },
        });
    }
}

// ── Registry entries ─────────────────────────────────────────────────────────

registry.category("fields").add("pdc_pie_chart", {
    component:      PDCPieChart,
    supportedTypes: ["json"],
});

registry.category("fields").add("pdc_bar_chart", {
    component:      PDCBarChart,
    supportedTypes: ["json"],
});

registry.category("fields").add("pdc_line_chart", {
    component:      PDCLineChart,
    supportedTypes: ["json"],
});
