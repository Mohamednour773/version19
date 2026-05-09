/** @odoo-module **/

import { Component, useState, useEffect } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

/**
 * ClubReceiptSection
 *
 * Shows active club memberships on the POS receipt for whoever
 * is set as the order's customer.
 *
 * Approach: search by partner_id (stable integer) rather than trying
 * to trace memberships back to this specific order's lines.
 * This works on any receipt — package sale, service sale, anything —
 * as long as the customer has active memberships in the system.
 */
export class ClubReceiptSection extends Component {
    static template = "club_management_pos_ui.ClubReceiptSection";
    static props = {
        order: { type: Object, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.state = useState({ memberships: [] });

        useEffect(
            () => {
                const partnerId = this._getPartnerId();
                console.log(
                    "[ClubReceiptSection] effect — partnerId=", partnerId,
                    "| orderName=", this.props.order?.name
                );
                if (partnerId) {
                    this._loadMemberships(partnerId);
                } else {
                    this.state.memberships = [];
                }
            },
            () => [this._getPartnerId()]
        );
    }

    /**
     * Extract a numeric partner ID from the order, regardless of how
     * Odoo 19's reactive model exposes it (method vs property).
     */
    _getPartnerId() {
        const order = this.props.order;
        if (!order) return null;

        // Reactive POS model uses getPartner()
        const partner = order.getPartner?.() || order.partner_id;
        if (!partner) return null;

        if (typeof partner === "number") return partner;
        if (partner.id) return partner.id;
        return null;
    }

    async _loadMemberships(partnerId) {
        console.log("[ClubReceiptSection] calling get_partner_receipt_memberships, partnerId=", partnerId);
        try {
            const result = await this.orm.call(
                "club.membership",
                "get_partner_receipt_memberships",
                [partnerId]
            );
            console.log("[ClubReceiptSection] result:", result?.length ?? 0, "membership(s):", result);
            this.state.memberships = result || [];
        } catch (e) {
            console.error("[ClubReceiptSection] RPC failed:", e);
            this.state.memberships = [];
        }
    }

    get hasMemberships() {
        return this.state.memberships.length > 0;
    }
}
