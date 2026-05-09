/** @odoo-module **/
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onMounted } from "@odoo/owl";

const ACTION_XML_IDS = {
    action_report_cash: "club_management_system_final.action_report_cash",
    action_report_trainer_revenue: "club_management_system_final.action_report_trainer_revenue",
    action_report_session_utilization: "club_management_system_final.action_report_session_utilization",
    action_club_trainer_commission: "club_management_system_final.action_club_trainer_commission",
    action_club_membership: "club_management_system_final.action_club_membership",
};

class ClubReportDashboard extends Component {
    static template = "ReportDashboard";

    setup() {
        this.orm    = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state  = useState({
            loading: true,
            kpis: {},
            charts: {},
            recent: [],
            updated: "",
        });
        onMounted(() => this.load());
    }

    async load() {
        this.state.loading = true;
        try {
            const d = await this.orm.call(
                "club.report.dashboard",
                "get_data",
                [],
                {}
            );
            this.state.kpis    = d.kpis || {};
            this.state.charts  = d.charts || {};
            this.state.recent  = d.recent_transactions || [];
            this.state.updated = new Date().toLocaleTimeString("ar-EG");
            // Draw charts after DOM update
            setTimeout(() => this._drawCharts(), 50);
        } catch (e) {
            console.error(e);
            this.state.kpis = {};
            this.state.charts = {};
            this.state.recent = [];
            this.notification.add("تعذر تحميل بيانات لوحة التقارير.", {
                title: "Dashboard",
                type: "danger",
            });
        } finally {
            this.state.loading = false;
        }
    }

    _drawCharts() {
        const c = this.state.charts;
        if (!c) return;

        // Chart 1 — Revenue by Payment Method (Doughnut)
        const ctx1 = document.getElementById("chart-method");
        if (ctx1 && window.Chart) {
            if (ctx1._chart) ctx1._chart.destroy();
            const labels = Object.keys(c.revenue_by_method || {});
            const data   = Object.values(c.revenue_by_method || {});
            ctx1._chart  = new Chart(ctx1, {
                type: "doughnut",
                data: {
                    labels,
                    datasets: [{ data,
                        backgroundColor: ["#27ae60","#714B67","#2980b9","#e67e22"],
                        borderWidth: 2, borderColor: "#fff",
                    }],
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    plugins: {
                        legend: { position: "right", labels: { font: { size: 11 } } },
                    },
                },
            });
        }

        // Chart 2 — Top Trainers (Horizontal Bar)
        const ctx2 = document.getElementById("chart-trainers");
        if (ctx2 && window.Chart) {
            if (ctx2._chart) ctx2._chart.destroy();
            const trainers = c.top_trainers || [];
            ctx2._chart = new Chart(ctx2, {
                type: "bar",
                data: {
                    labels: trainers.map(t => t.name),
                    datasets: [{
                        label: "Commission (AED)",
                        data: trainers.map(t => t.amount),
                        backgroundColor: "#714B67",
                        borderRadius: 4,
                    }],
                },
                options: {
                    indexAxis: "y",
                    responsive: true, maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { grid: { display: false } },
                        y: { grid: { display: false }, ticks: { font: { size: 11 } } },
                    },
                },
            });
        }

        // Chart 3 — Daily Attendance (Line)
        const ctx3 = document.getElementById("chart-attendance");
        if (ctx3 && window.Chart) {
            if (ctx3._chart) ctx3._chart.destroy();
            const daily = c.daily_attendance || [];
            ctx3._chart = new Chart(ctx3, {
                type: "line",
                data: {
                    labels: daily.map(d => d.date),
                    datasets: [{
                        label: "Attended",
                        data: daily.map(d => d.count),
                        borderColor: "#27ae60",
                        backgroundColor: "rgba(39,174,96,0.08)",
                        tension: 0.4, fill: true,
                        pointBackgroundColor: "#27ae60",
                        pointRadius: 4,
                    }],
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        y: { beginAtZero: true, ticks: { stepSize: 1 } },
                        x: { grid: { display: false } },
                    },
                },
            });
        }

        // Chart 4 — Utilization Bar (Group vs Private)
        const ctx4 = document.getElementById("chart-utilization");
        if (ctx4 && window.Chart) {
            if (ctx4._chart) ctx4._chart.destroy();
            const util = c.utilization || {};
            ctx4._chart = new Chart(ctx4, {
                type: "bar",
                data: {
                    labels: ["Group Classes", "Private Sessions"],
                    datasets: [{
                        label: "Utilization %",
                        data: [util.group || 0, util.private || 0],
                        backgroundColor: ["#2980b9", "#e67e22"],
                        borderRadius: 6,
                    }],
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        y: { beginAtZero: true, max: 100,
                             ticks: { callback: v => v + "%" } },
                        x: { grid: { display: false } },
                    },
                },
            });
        }
    }

    fmt(amount) {
        return new Intl.NumberFormat("en-AE", {
            minimumFractionDigits: 0, maximumFractionDigits: 0,
        }).format(amount || 0) + " AED";
    }

    pctChange(current, prev) {
        if (!prev) return null;
        const pct = Math.round(((current - prev) / prev) * 100);
        return { value: Math.abs(pct), up: pct >= 0 };
    }

    async openReport(xmlId) {
        try {
            await this.action.doAction(ACTION_XML_IDS[xmlId] || xmlId);
        } catch (e) {
            console.error(e);
            this.notification.add("تعذر فتح التقرير المطلوب من لوحة التقارير.", {
                title: "Dashboard",
                type: "warning",
            });
        }
    }

    async openMembership(id) {
        try {
            await this.action.doAction({
                type: "ir.actions.act_window",
                res_model: "club.membership",
                res_id: id,
                views: [[false, "form"]],
                target: "current",
            });
        } catch (e) {
            console.error(e);
            this.notification.add("تعذر فتح الاشتراك من الجدول الأخير.", {
                title: "Dashboard",
                type: "warning",
            });
        }
    }
}

registry.category("actions").add(
    "ReportDashboard",
    ClubReportDashboard
);
