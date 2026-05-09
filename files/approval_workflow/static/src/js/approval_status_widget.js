/** @odoo-module **/

/**
 * Approval Status Widget
 * Displays a visual stage progress indicator on any form view
 * that has approval requests linked.
 */

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onWillStart, onWillUpdateProps } from "@odoo/owl";

/**
 * ApprovalStatusWidget
 * A field widget that shows the visual approval stage progress bar.
 * Use it in a view like:
 *   <field name="approval_state" widget="approval_status"/>
 */
class ApprovalStatusWidget extends Component {
    static template = "approval_workflow.ApprovalStatusWidget";
    static props = {
        record: Object,
        name: String,
    };

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");

        this.state = useState({
            stages: [],
            currentState: "none",
            requestId: null,
            waitingOn: "",
            loading: true,
        });

        onWillStart(async () => {
            await this._loadApprovalData();
        });

        onWillUpdateProps(async () => {
            await this._loadApprovalData();
        });
    }

    async _loadApprovalData() {
        const record = this.props.record;
        const modelName = record.resModel;
        const recordId = record.resId;

        if (!recordId) {
            this.state.loading = false;
            return;
        }

        try {
            // Find active approval request
            const requests = await this.orm.searchRead(
                "approval.request",
                [
                    ["res_model", "=", modelName],
                    ["res_id", "=", recordId],
                    ["state", "not in", ["cancelled"]],
                ],
                ["id", "state", "current_stage_id", "waiting_on", "line_ids"],
                { order: "create_date desc", limit: 1 }
            );

            if (!requests.length) {
                this.state.currentState = "none";
                this.state.stages = [];
                this.state.requestId = null;
                this.state.loading = false;
                return;
            }

            const req = requests[0];
            this.state.requestId = req.id;
            this.state.currentState = req.state;
            this.state.waitingOn = req.waiting_on || "";

            // Load stage lines for visual progress
            if (req.line_ids && req.line_ids.length > 0) {
                const lines = await this.orm.searchRead(
                    "approval.request.line",
                    [["request_id", "=", req.id]],
                    ["stage_name", "stage_sequence", "state", "approver_id"],
                    { order: "stage_sequence asc, id asc" }
                );

                // Deduplicate by stage (show one bubble per stage)
                const stageMap = {};
                for (const line of lines) {
                    const key = line.stage_name;
                    if (!stageMap[key]) {
                        stageMap[key] = {
                            name: line.stage_name,
                            sequence: line.stage_sequence,
                            state: line.state,
                        };
                    } else {
                        // If any line in stage is refused → refused
                        if (line.state === "refused") {
                            stageMap[key].state = "refused";
                        }
                        // If stage has a mix of approved + pending → pending
                        if (
                            stageMap[key].state === "approved" &&
                            line.state === "pending"
                        ) {
                            stageMap[key].state = "pending";
                        }
                    }
                }
                this.state.stages = Object.values(stageMap).sort(
                    (a, b) => a.sequence - b.sequence
                );
            }
        } catch (e) {
            console.warn("ApprovalStatusWidget: could not load data", e);
        }
        this.state.loading = false;
    }

    getStageClass(stage) {
        if (stage.state === "approved") return "approved";
        if (stage.state === "refused") return "refused";
        if (stage.state === "pending") {
            const req = this.state;
            if (req.currentState === "in_progress") return "current";
            return "pending";
        }
        return "";
    }

    getStageIcon(stage) {
        if (stage.state === "approved") return "fa-check";
        if (stage.state === "refused") return "fa-times";
        return null;
    }

    async openRequest() {
        if (!this.state.requestId) return;
        await this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "approval.request",
            res_id: this.state.requestId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    getStatusLabel() {
        const labels = {
            none: "No Approval",
            draft: "Draft",
            pending: "Pending",
            in_progress: "In Progress",
            approved: "Approved",
            refused: "Refused",
            cancelled: "Cancelled",
        };
        return labels[this.state.currentState] || this.state.currentState;
    }

    getStatusClass() {
        return `state_${this.state.currentState}`;
    }
}

ApprovalStatusWidget.template = "approval_workflow.ApprovalStatusWidget";

// Register as a field widget
registry.category("fields").add("approval_status", {
    component: ApprovalStatusWidget,
    displayName: "Approval Status",
    supportedTypes: ["char", "selection"],
});


/**
 * OWL Template for the approval status widget.
 * Registered inline since we're not using a separate XML file.
 */
import { xml } from "@odoo/owl";

ApprovalStatusWidget.template = xml`
<div class="approval_status_widget">
    <t t-if="state.loading">
        <span class="text-muted"><i class="fa fa-spinner fa-spin"/> Loading...</span>
    </t>
    <t t-elif="state.currentState === 'none'">
        <span class="approval_status_badge state_none">
            <i class="fa fa-circle-o"/>
            No Approval
        </span>
    </t>
    <t t-else="">
        <!-- Status badge -->
        <div style="display:flex; align-items:center; gap:10px; margin-bottom:8px;">
            <span t-att-class="'approval_status_badge ' + getStatusClass()"
                  style="cursor:pointer"
                  t-on-click="openRequest">
                <t t-if="state.currentState === 'approved'">
                    <i class="fa fa-check-circle"/>
                </t>
                <t t-elif="state.currentState === 'refused'">
                    <i class="fa fa-times-circle"/>
                </t>
                <t t-elif="state.currentState in ['pending','in_progress']">
                    <span class="approval_pending_dot"/>
                </t>
                <t t-esc="getStatusLabel()"/>
            </span>
            <t t-if="state.waitingOn and state.currentState in ['pending','in_progress']">
                <span class="text-muted" style="font-size:12px;">
                    Waiting on: <strong t-esc="state.waitingOn"/>
                </span>
            </t>
        </div>

        <!-- Stage step indicators -->
        <t t-if="state.stages.length > 0">
            <ul class="approval_stage_steps">
                <t t-foreach="state.stages" t-as="stage" t-key="stage.name">
                    <li t-att-class="'step ' + getStageClass(stage)"
                        t-att-title="stage.name + ': ' + stage.state">
                        <div class="dot">
                            <t t-if="getStageIcon(stage)">
                                <i t-att-class="'fa ' + getStageIcon(stage)"/>
                            </t>
                            <t t-else="">
                                <t t-esc="stage_index + 1"/>
                            </t>
                        </div>
                        <div class="label" t-esc="stage.name"/>
                    </li>
                </t>
            </ul>
        </t>

        <!-- Click to view -->
        <div style="margin-top:4px;">
            <a href="#" t-on-click.prevent="openRequest"
               style="font-size:11px; color:#007bff; text-decoration:none;">
                <i class="fa fa-external-link-square"/> View Approval Request
            </a>
        </div>
    </t>
</div>
`;

export { ApprovalStatusWidget };
