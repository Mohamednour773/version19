/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { _t } from "@web/core/l10n/translation";

patch(PaymentScreen.prototype, {
    async validateOrder(isForceValidate) {
        const pos = this.pos;
        const config = pos.config;
        if (!config?.prevent_negative_stock) {
            return super.validateOrder(...arguments);
        }

        if (pos.data?.network?.online) {
            await pos.refreshAllProductStock();
        }

        const order = pos.get_order();
        const lines = order.get_orderlines();

        for (const line of lines) {
            const product = line.get_product();
            if (!product || line.is_negative_override) {
                continue;
            }
            const qty = line.get_quantity();
            if (qty <= 0) {
                continue;
            }
            const result = await pos.checkNegativeStock(product, qty, {
                excludeLineId: line.id,
            });
            if (!result.allowed) {
                return;
            }
            if (result.override) {
                line.is_negative_override = true;
                line.override_user_id = result.overrideUserId;
                line.override_reason = result.overrideReason;
            }
        }

        return super.validateOrder(...arguments);
    },
});
