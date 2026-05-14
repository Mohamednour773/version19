from odoo import api, fields, models


class PosSession(models.Model):
    _inherit = "pos.session"

    @api.model
    def _loader_params_product_product(self):
        result = super()._loader_params_product_product()
        result["search_params"]["fields"].extend([
            "qty_available",
            "virtual_available",
            "incoming_qty",
            "outgoing_qty",
            "free_qty",
            "type",
        ])
        return result

    def _get_pos_ui_product_product(self, params):
        result = super()._get_pos_ui_product_product(params)
        config = self.config_id
        if not config.prevent_negative_stock:
            return result
        warehouse = config.picking_type_id.warehouse_id
        if not warehouse:
            return result
        product_ids = [p["id"] for p in result]
        if not product_ids:
            return result
        products = self.env["product.product"].browse(product_ids).with_context(
            warehouse=warehouse.id,
        )
        stock_map = {}
        for product in products:
            stock_map[product.id] = {
                "qty_available": product.qty_available,
                "virtual_available": product.virtual_available,
                "incoming_qty": product.incoming_qty,
                "outgoing_qty": product.outgoing_qty,
                "free_qty": product.free_qty,
            }
        for product_data in result:
            pid = product_data["id"]
            if pid in stock_map:
                product_data.update(stock_map[pid])
        return result

    @api.model
    def get_product_stock_levels(self, product_ids, warehouse_id):
        """Batch RPC endpoint for on-demand stock refresh.

        Returns: {product_id: {on_hand, available, forecasted, free_qty}}
        """
        if not product_ids or not warehouse_id:
            return {}
        products = self.env["product.product"].browse(product_ids).with_context(
            warehouse=warehouse_id,
        )
        result = {}
        for product in products:
            result[product.id] = {
                "on_hand": product.qty_available,
                "available": product.free_qty,
                "forecasted": product.virtual_available,
                "incoming_qty": product.incoming_qty,
                "outgoing_qty": product.outgoing_qty,
                "free_qty": product.free_qty,
            }
        return result
