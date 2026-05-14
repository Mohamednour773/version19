from odoo import api, models


class ProductProduct(models.Model):
    _inherit = "product.product"

    @api.model
    def _get_pos_available_qty(self, warehouse_id, mode="available"):
        """Return the stock quantity for the given mode in the specified warehouse."""
        self_ctx = self.with_context(warehouse=warehouse_id)
        if mode == "on_hand":
            return self_ctx.qty_available
        if mode == "forecasted":
            return self_ctx.virtual_available
        return self_ctx.free_qty
