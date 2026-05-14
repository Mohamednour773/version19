/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
import { PosOrder } from "@point_of_sale/app/models/pos_order";

patch(PosOrderline.prototype, {
    setup() {
        super.setup(...arguments);
        this.is_negative_override = this.is_negative_override || false;
        this.override_user_id = this.override_user_id || false;
        this.override_reason = this.override_reason || "";
    },

    getPackingDetails() {
        const details = super.getPackingDetails(...arguments);
        return details;
    },

    export_as_JSON() {
        const json = super.export_as_JSON(...arguments);
        json.is_negative_override = this.is_negative_override || false;
        json.override_user_id = this.override_user_id || false;
        json.override_reason = this.override_reason || "";
        return json;
    },

    init_from_JSON(json) {
        super.init_from_JSON(json);
        this.is_negative_override = json.is_negative_override || false;
        this.override_user_id = json.override_user_id || false;
        this.override_reason = json.override_reason || "";
    },
});

patch(PosOrder.prototype, {
    export_as_JSON() {
        const json = super.export_as_JSON(...arguments);
        return json;
    },
});
