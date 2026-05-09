/** @odoo-module **/

import { Component, useState, useEffect } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";

// Simple 30-second in-memory cache keyed by partner_id
const _infoCache = new Map();
const CACHE_TTL_MS = 30_000;

function getCached(partnerId) {
    const entry = _infoCache.get(partnerId);
    if (!entry) return null;
    if (Date.now() - entry.ts > CACHE_TTL_MS) {
        _infoCache.delete(partnerId);
        return null;
    }
    return entry.data;
}

function setCache(partnerId, data) {
    _infoCache.set(partnerId, { ts: Date.now(), data });
}

/**
 * Extract a numeric branch ID safely, regardless of whether
 * club_branch_id arrives as a number, [id, name] tuple, or a model instance.
 */
function extractId(val) {
    if (!val) return false;
    if (typeof val === "number") return val;
    if (Array.isArray(val)) return val[0] || false;
    if (typeof val === "object") return val.id || false;
    return false;
}

export class CustomerInfoCard extends Component {
    static template = "club_management_pos_ui.CustomerInfoCard";
    static props = {};

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.pos = usePos();

        this.state = useState({
            loading: false,
            info: null,      // result from get_club_pos_info
            checkingIn: false,
        });

        // Re-fetch whenever the partner on the current order changes
        useEffect(
            () => {
                const partner = this.pos.getOrder()?.getPartner();
                if (partner) {
                    this._loadInfo(partner.id);
                } else {
                    this.state.info = null;
                }
            },
            () => [this.pos.getOrder()?.getPartner()?.id]
        );
    }

    async _loadInfo(partnerId) {
        const cached = getCached(partnerId);
        if (cached) {
            this.state.info = cached;
            return;
        }

        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "res.partner",
                "get_club_pos_info",
                [partnerId]
            );
            setCache(partnerId, data);
            this.state.info = data;
        } catch (e) {
            console.error("CustomerInfoCard: failed to load club info", e);
            this.state.info = null;
        } finally {
            this.state.loading = false;
        }
    }

    get showCard() {
        return !!this.pos.getOrder()?.getPartner();
    }

    get enableCheckin() {
        return !!this.pos.config.club_enable_pos_checkin;
    }

    get currentPartnerId() {
        return this.pos.getOrder()?.getPartner()?.id || false;
    }

    get currentBranchId() {
        return extractId(this.pos.config.club_branch_id);
    }

    async onCheckin() {
        if (!this.currentPartnerId) return;
        this.state.checkingIn = true;
        try {
            const result = await this.orm.call(
                "club.attendance",
                "pos_check_in_partner",
                [this.currentPartnerId, this.currentBranchId]
            );
            // Map backend status codes to notification types
            const typeMap = {
                ok:             "success",
                already_marked: "info",
                no_session:     "warning",
                no_membership:  "warning",
                error:          "danger",
            };
            const type   = typeMap[result.status] ?? "danger";
            const sticky = result.status === "error";
            this.notification.add(result.message, { type, sticky });

            // Refresh card only when the check-in state actually changed
            if (result.status === "ok" || result.status === "already_marked") {
                _infoCache.delete(this.currentPartnerId);
                await this._loadInfo(this.currentPartnerId);
            }
        } catch (e) {
            // Never expose raw RPC / SQL errors to the cashier
            console.error("CustomerInfoCard: check-in RPC failed", e);
            this.notification.add(
                "حدث خطأ أثناء تسجيل الحضور. يرجى المحاولة مرة أخرى. / Check-in failed. Please try again.",
                { type: "danger", sticky: false }
            );
        } finally {
            this.state.checkingIn = false;
        }
    }
}
