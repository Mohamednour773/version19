/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { _t } from "@web/core/l10n/translation";

patch(ProductScreen.prototype, {
    async _onClickProduct(event) {
        const product = event.detail || event;
        if (!product?.id) {
            return super._onClickProduct(...arguments);
        }
        const pos = this.pos;
        if (!pos.config?.prevent_negative_stock) {
            return super._onClickProduct(...arguments);
        }
        const result = await pos.checkNegativeStock(product, 1);
        if (!result.allowed) {
            return;
        }
        const res = await super._onClickProduct(...arguments);
        if (result.override) {
            const order = pos.get_order();
            const lines = order.get_orderlines();
            const lastLine = lines[lines.length - 1];
            if (lastLine && lastLine.get_product()?.id === product.id) {
                lastLine.is_negative_override = true;
                lastLine.override_user_id = result.overrideUserId;
                lastLine.override_reason = result.overrideReason;
            }
        }
        return res;
    },

    async refreshStock() {
        await this.pos.refreshAllProductStock();
        this.notification.add(_t("Stock levels refreshed"), { type: "info" });
    },
});
