/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";

class PettyCashDashboard extends Component {
    static template = "petty_cash_management.Dashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            funds: [],
            pendingCount: 0,
            overdueCount: 0,
            totalBalance: 0,
            expensesByCategory: [],
            monthlySpend: [],
            isLoading: true,
        });
        onWillStart(async () => {
            await this._loadData();
        });
    }

    async _loadData() {
        try {
            // Load active funds
            const funds = await this.orm.searchRead(
                "petty.cash.fund",
                [["state", "=", "active"]],
                ["name", "name_ar", "current_balance", "min_balance", "currency_id", "custodian_id"],
                { limit: 10 }
            );
            this.state.funds = funds;
            this.state.totalBalance = funds.reduce((s, f) => s + f.current_balance, 0);

            // Pending approvals
            const pending = await this.orm.searchCount("hr.petty.cash", [
                ["state", "=", "waiting_approval"],
            ]);
            this.state.pendingCount = pending;

            // Overdue custodies
            const today = new Date().toISOString().split("T")[0];
            const overdue = await this.orm.searchCount("hr.petty.cash", [
                ["state", "=", "paid"],
                ["expected_return_date", "<", today],
            ]);
            this.state.overdueCount = overdue;

            // Expenses by category (last 30 days)
            const thirtyDaysAgo = new Date();
            thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);
            const dateStr = thirtyDaysAgo.toISOString().split("T")[0];

            const lines = await this.orm.searchRead(
                "petty.cash.settlement.line",
                [["expense_date", ">=", dateStr]],
                ["category_id", "total_amount"],
                { limit: 1000 }
            );

            // Group by category
            const catMap = {};
            for (const line of lines) {
                const catName = line.category_id ? line.category_id[1] : "Other";
                catMap[catName] = (catMap[catName] || 0) + line.total_amount;
            }
            this.state.expensesByCategory = Object.entries(catMap)
                .map(([name, amount]) => ({ name, amount }))
                .sort((a, b) => b.amount - a.amount)
                .slice(0, 6);

            this.state.isLoading = false;
        } catch (e) {
            console.error("Petty Cash Dashboard error:", e);
            this.state.isLoading = false;
        }
    }

    openFunds() {
        this.action.doAction("petty_cash_management.action_petty_cash_fund");
    }

    openPending() {
        this.action.doAction("petty_cash_management.action_hr_petty_cash_pending");
    }

    openOverdue() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Overdue Custodies",
            res_model: "hr.petty.cash",
            view_mode: "list,form",
            domain: [["state", "=", "paid"], ["expected_return_date", "<", new Date().toISOString().split("T")[0]]],
        });
    }

    openCustodies() {
        this.action.doAction("petty_cash_management.action_hr_petty_cash_all");
    }

    openSettlements() {
        this.action.doAction("petty_cash_management.action_petty_cash_settlement");
    }
}

// Register as a list controller override (dashboard mode)
registry.category("views").add("petty_cash_dashboard", {
    ...registry.category("views").get("list"),
    Controller: PettyCashDashboard,
});

export { PettyCashDashboard };
