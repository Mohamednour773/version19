/** @odoo-module **/
/**
 * APW Approval Status Widget
 * Shows visual stage progress on any form view.
 * Register in a view as: <field name="apw_state" widget="apw_status"/>
 */

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onWillStart, onWillUpdateProps, xml } from "@odoo/owl";

class ApwStatusWidget extends Component {
    static props = { record: Object, name: String };

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.state = useState({
            stages: [], currentState: "none",
            requestId: null, waitingOn: "", loading: true,
        });
        onWillStart(async () => { await this._load(); });
        onWillUpdateProps(async () => { await this._load(); });
    }

    async _load() {
        const { resModel, resId } = this.props.record;
        if (!resId) { this.state.loading = false; return; }
        try {
            const reqs = await this.orm.searchRead(
                "apw.request",
                [["res_model","=",resModel],["res_id","=",resId],["state","not in",["cancelled"]]],
                ["id","state","current_stage_id","waiting_on","line_ids"],
                { order: "create_date desc", limit: 1 }
            );
            if (!reqs.length) {
                Object.assign(this.state, { currentState:"none", stages:[], requestId:null });
                this.state.loading = false; return;
            }
            const req = reqs[0];
            this.state.requestId = req.id;
            this.state.currentState = req.state;
            this.state.waitingOn = req.waiting_on || "";

            if (req.line_ids?.length) {
                const lines = await this.orm.searchRead(
                    "apw.request.line",
                    [["request_id","=",req.id]],
                    ["stage_name","stage_sequence","state"],
                    { order: "stage_sequence asc, id asc" }
                );
                const stageMap = {};
                for (const l of lines) {
                    if (!stageMap[l.stage_name]) {
                        stageMap[l.stage_name] = { name: l.stage_name, sequence: l.stage_sequence, state: l.state };
                    } else {
                        if (l.state === "refused") stageMap[l.stage_name].state = "refused";
                        if (stageMap[l.stage_name].state === "approved" && l.state === "pending")
                            stageMap[l.stage_name].state = "pending";
                    }
                }
                this.state.stages = Object.values(stageMap).sort((a,b) => a.sequence - b.sequence);
            }
        } catch(e) { console.warn("ApwStatusWidget error:", e); }
        this.state.loading = false;
    }

    stageClass(s) {
        if (s.state === "approved") return "approved";
        if (s.state === "refused") return "refused";
        if (s.state === "pending" && this.state.currentState === "in_progress") return "current";
        return "";
    }

    statusLabel() {
        return { none:"No Approval", draft:"Draft", pending:"Pending",
                 in_progress:"In Progress", approved:"Approved", refused:"Refused",
                 cancelled:"Cancelled" }[this.state.currentState] || this.state.currentState;
    }

    async openRequest() {
        if (!this.state.requestId) return;
        await this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "apw.request",
            res_id: this.state.requestId,
            views: [[false, "form"]],
            target: "current",
        });
    }
}

ApwStatusWidget.template = xml`
<div class="apw_status_widget">
    <t t-if="state.loading">
        <span class="text-muted"><i class="fa fa-spinner fa-spin"/> Loading...</span>
    </t>
    <t t-elif="state.currentState === 'none'">
        <span class="apw_status_badge state_none"><i class="fa fa-circle-o"/> No Approval</span>
    </t>
    <t t-else="">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">
            <span t-att-class="'apw_status_badge state_' + state.currentState"
                  style="cursor:pointer" t-on-click="openRequest">
                <t t-if="state.currentState === 'approved'"><i class="fa fa-check-circle"/></t>
                <t t-elif="state.currentState === 'refused'"><i class="fa fa-times-circle"/></t>
                <t t-elif="state.currentState in ['pending','in_progress']">
                    <span class="apw_pending_dot"/>
                </t>
                <t t-esc="statusLabel()"/>
            </span>
            <t t-if="state.waitingOn and state.currentState in ['pending','in_progress']">
                <span class="text-muted" style="font-size:12px;">
                    Waiting on: <strong t-esc="state.waitingOn"/>
                </span>
            </t>
        </div>
        <t t-if="state.stages.length > 0">
            <ul class="apw_stage_steps">
                <t t-foreach="state.stages" t-as="stage" t-key="stage.name">
                    <li t-att-class="'step ' + stageClass(stage)" t-att-title="stage.name">
                        <div class="dot">
                            <t t-if="stage.state === 'approved'"><i class="fa fa-check"/></t>
                            <t t-elif="stage.state === 'refused'"><i class="fa fa-times"/></t>
                            <t t-else=""><t t-esc="stage_index + 1"/></t>
                        </div>
                        <div class="label" t-esc="stage.name"/>
                    </li>
                </t>
            </ul>
        </t>
        <div style="margin-top:4px;">
            <a href="#" t-on-click.prevent="openRequest"
               style="font-size:11px;color:#007bff;text-decoration:none;">
                <i class="fa fa-external-link-square"/> View Approval Request
            </a>
        </div>
    </t>
</div>
`;

registry.category("fields").add("apw_status", {
    component: ApwStatusWidget,
    displayName: "APW Approval Status",
    supportedTypes: ["char", "selection"],
});

export { ApwStatusWidget };
