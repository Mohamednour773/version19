/** @odoo-module */

import { Component, useState } from "@odoo/owl";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

export class NegativeStockPopup extends Component {
    static template = "pos_prevent_negative_stock.NegativeStockPopup";
    static props = {
        product: Object,
        available: Number,
        requested: Number,
        noOverride: { type: Boolean, optional: true },
        requireReason: { type: Boolean, optional: true },
        title: { type: String, optional: true },
        close: { type: Function, optional: true },
    };

    setup() {
        this.pos = usePos();
        this.notification = useService("notification");
        this.state = useState({
            showPin: false,
            pin: "",
            reason: "",
            pinError: "",
        });
    }

    cancel() {
        this.props.close?.({ confirmed: false });
    }

    requestOverride() {
        this.state.showPin = true;
        this.state.pin = "";
        this.state.pinError = "";
    }

    onPinInput(ev) {
        this.state.pin = ev.target.value;
        this.state.pinError = "";
    }

    onReasonInput(ev) {
        this.state.reason = ev.target.value;
    }

    onPinKeydown(ev) {
        if (ev.key === "Enter") {
            this.confirmOverride();
        }
    }

    async confirmOverride() {
        const pin = this.state.pin;
        if (!pin) {
            this.state.pinError = _t("Please enter a PIN.");
            return;
        }
        if (this.props.requireReason && !this.state.reason.trim()) {
            this.state.pinError = _t("Please enter an override reason.");
            return;
        }
        const config = this.pos.config;
        const overrideGroupId = config.override_user_group_id?.[0]
            || config.override_user_group_id?.id;
        const employees = this.pos.models["hr.employee"]
            ? Object.values(this.pos.models["hr.employee"])
            : [];
        const cashiers = this.pos.models["res.users"]
            ? Object.values(this.pos.models["res.users"])
            : [];
        let overrideUser = null;

        for (const emp of employees) {
            if (emp.pin === pin || String(emp.pin) === pin) {
                const user = cashiers.find((u) => u.id === emp.user_id?.[0] || u.id === emp.user_id?.id);
                if (user) {
                    const userGroupIds = (user.groups_id || []).map((g) => g.id || g);
                    const managerGroupId = this.pos.data?.models?.["ir.model.data"]
                        ? null
                        : null;
                    if (
                        !overrideGroupId ||
                        userGroupIds.includes(overrideGroupId) ||
                        user.role === "manager"
                    ) {
                        overrideUser = user;
                        break;
                    }
                }
            }
        }

        if (!overrideUser) {
            for (const user of cashiers) {
                if (user.pin === pin || String(user.pin) === pin) {
                    const userGroupIds = (user.groups_id || []).map((g) => g.id || g);
                    if (
                        !overrideGroupId ||
                        userGroupIds.includes(overrideGroupId) ||
                        user.role === "manager"
                    ) {
                        overrideUser = user;
                        break;
                    }
                }
            }
        }

        if (!overrideUser) {
            this.state.pinError = _t("Invalid PIN or insufficient permissions.");
            return;
        }

        this.notification.add(
            _t("Override applied by %s", overrideUser.name),
            { type: "success" }
        );

        this.props.close?.({
            confirmed: true,
            payload: {
                overrideUser,
                reason: this.state.reason,
            },
        });
    }
}
