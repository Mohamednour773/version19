/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/store/pos_store";
import { _t } from "@web/core/l10n/translation";

patch(PosStore.prototype, {
    async setup() {
        await super.setup(...arguments);
        this._stockRefreshTimer = null;
        this._startStockRefreshInterval();
    },

    _startStockRefreshInterval() {
        this._stopStockRefreshInterval();
        const config = this.config;
        if (!config?.prevent_negative_stock) {
            return;
        }
        const interval = (config.refresh_stock_interval || 60) * 1000;
        this._stockRefreshTimer = setInterval(async () => {
            if (this.data?.network?.online) {
                await this.refreshAllProductStock();
            }
        }, interval);
    },

    _stopStockRefreshInterval() {
        if (this._stockRefreshTimer) {
            clearInterval(this._stockRefreshTimer);
            this._stockRefreshTimer = null;
        }
    },

    async refreshAllProductStock() {
        const config = this.config;
        if (!config?.prevent_negative_stock) {
            return;
        }
        const warehouseId = config.picking_type_id?.warehouse_id;
        if (!warehouseId) {
            return;
        }
        const productIds = Object.keys(this.models["product.product"] || {}).map(Number);
        if (!productIds.length) {
            return;
        }
        try {
            const stockData = await this.data.call(
                "pos.session",
                "get_product_stock_levels",
                [productIds, warehouseId[0] || warehouseId],
            );
            for (const [pidStr, levels] of Object.entries(stockData)) {
                const pid = Number(pidStr);
                const product = this.models["product.product"]?.[pid];
                if (product) {
                    product.qty_available = levels.on_hand;
                    product.virtual_available = levels.forecasted;
                    product.free_qty = levels.free_qty;
                    product.incoming_qty = levels.incoming_qty;
                    product.outgoing_qty = levels.outgoing_qty;
                }
            }
        } catch {
            // Offline or RPC failure — use cached stock
        }
    },

    getAvailableQty(product) {
        const config = this.config;
        const mode = config?.negative_stock_check_mode || "available";
        let qty;
        if (mode === "on_hand") {
            qty = product.qty_available || 0;
        } else if (mode === "forecasted") {
            qty = product.virtual_available || 0;
        } else {
            qty = product.free_qty || 0;
        }
        const bufferPct = parseFloat(
            this.config?.company?.system_parameters?.["pos_negative_stock.offline_buffer_pct"] || "0"
        );
        if (bufferPct > 0 && !this.data?.network?.online) {
            qty = qty * (1 - bufferPct / 100);
        }
        return qty;
    },

    getOrderQtyForProduct(product, excludeLineId) {
        const order = this.get_order();
        if (!order) {
            return 0;
        }
        let totalQty = 0;
        for (const line of order.get_orderlines()) {
            if (line.get_product()?.id === product.id) {
                if (excludeLineId && line.id === excludeLineId) {
                    continue;
                }
                totalQty += line.get_quantity();
            }
        }
        return totalQty;
    },

    isProductExcluded(product) {
        const config = this.config;
        if (!config?.prevent_negative_stock) {
            return true;
        }
        if (!config.block_unstorable_products && product.type !== "product") {
            return true;
        }
        const excludedCategIds = (config.excluded_product_categ_ids || []).map(
            (c) => c.id || c
        );
        if (excludedCategIds.includes(product.categ_id?.[0] || product.categ_id?.id)) {
            return true;
        }
        const excludedProductIds = (config.excluded_product_ids || []).map(
            (p) => p.id || p
        );
        if (excludedProductIds.includes(product.id)) {
            return true;
        }
        return false;
    },

    async checkNegativeStock(product, requestedQty, options = {}) {
        if (this.isProductExcluded(product)) {
            return { allowed: true };
        }
        const available = this.getAvailableQty(product);
        const inOrder = this.getOrderQtyForProduct(product, options.excludeLineId);
        const totalRequested = inOrder + requestedQty;

        if (available - totalRequested >= 0) {
            return { allowed: true };
        }

        const config = this.config;
        if (config.allow_manager_override) {
            const { confirmed, payload } = await this.popup.add(
                (await odoo.loader.modules.get(
                    "@pos_prevent_negative_stock/app/popups/negative_stock_popup"
                ))?.NegativeStockPopup,
                {
                    product,
                    available,
                    requested: totalRequested,
                    requireReason: config.require_override_reason,
                }
            );
            if (confirmed && payload?.overrideUser) {
                return {
                    allowed: true,
                    override: true,
                    overrideUserId: payload.overrideUser.id,
                    overrideReason: payload.reason || "",
                };
            }
            return { allowed: false };
        }

        await this.popup.add(
            (await odoo.loader.modules.get(
                "@pos_prevent_negative_stock/app/popups/negative_stock_popup"
            ))?.NegativeStockPopup,
            {
                product,
                available,
                requested: totalRequested,
                noOverride: true,
            }
        );
        return { allowed: false };
    },
});
