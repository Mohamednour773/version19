from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PosOrderLine(models.Model):
    _inherit = "pos.order.line"

    is_negative_override = fields.Boolean(
        string="Negative Stock Override",
        default=False,
        readonly=True,
        index=True,
        help="This line was sold despite insufficient stock, with manager approval.",
    )
    override_user_id = fields.Many2one(
        comodel_name="res.users",
        string="Override Approved By",
        readonly=True,
    )
    override_reason = fields.Char(
        string="Override Reason",
        readonly=True,
    )


class PosOrder(models.Model):
    _inherit = "pos.order"

    has_negative_override = fields.Boolean(
        string="Has Stock Override",
        compute="_compute_has_negative_override",
        store=True,
    )

    @api.depends("lines.is_negative_override")
    def _compute_has_negative_override(self):
        for order in self:
            order.has_negative_override = any(
                line.is_negative_override for line in order.lines
            )

    @api.model
    def _process_order(self, order, existing_order):
        pos_session = self.env["pos.session"].browse(order["data"]["pos_session_id"])
        config = pos_session.config_id
        if config.prevent_negative_stock:
            self._validate_stock_levels(order, config)
        return super()._process_order(order, existing_order)

    def _validate_stock_levels(self, order, config):
        warehouse = config.picking_type_id.warehouse_id
        if not warehouse:
            return
        excluded_categ_ids = set(config.excluded_product_categ_ids.ids)
        excluded_product_ids = set(config.excluded_product_ids.ids)
        override_group = (
            config.override_user_group_id
            or self.env.ref("point_of_sale.group_pos_manager", raise_if_not_found=False)
        )
        lines_data = order["data"].get("lines", [])
        product_qty_map = {}
        line_overrides = {}
        for line_entry in lines_data:
            line_vals = line_entry[2] if isinstance(line_entry, (list, tuple)) else line_entry
            product_id = line_vals.get("product_id")
            qty = line_vals.get("qty", 0)
            if not product_id or qty <= 0:
                continue
            product_qty_map.setdefault(product_id, 0)
            product_qty_map[product_id] += qty
            is_override = line_vals.get("is_negative_override", False)
            override_uid = line_vals.get("override_user_id", False)
            if is_override:
                line_overrides[product_id] = override_uid

        if not product_qty_map:
            return

        products = self.env["product.product"].browse(
            list(product_qty_map.keys())
        ).with_context(warehouse=warehouse.id)

        for product in products:
            if product.id in excluded_product_ids:
                continue
            if product.categ_id.id in excluded_categ_ids:
                continue
            if not config.block_unstorable_products and product.type != "product":
                continue

            available = self._get_qty_for_mode(product, config.negative_stock_check_mode)
            requested = product_qty_map.get(product.id, 0)

            if available - requested < 0:
                if config.allow_manager_override and product.id in line_overrides:
                    override_uid = line_overrides[product.id]
                    if override_uid and override_group:
                        user = self.env["res.users"].browse(override_uid)
                        if override_group.id in user.groups_id.ids:
                            continue
                    raise UserError(
                        _("Negative stock override rejected: user %(user)s is not in "
                          "the authorized override group.\n"
                          "رفض تجاوز المخزون السالب: المستخدم %(user)s ليس في "
                          "مجموعة التجاوز المعتمدة.",
                          user=override_uid)
                    )
                raise UserError(
                    _("Insufficient stock for %(product)s. "
                      "Available: %(available)s, Requested: %(requested)s. "
                      "Order rejected by server.\n"
                      "مخزون غير كافٍ للمنتج %(product)s. "
                      "المتاح: %(available)s، المطلوب: %(requested)s. "
                      "تم رفض الطلب من الخادم.",
                      product=product.display_name,
                      available=available,
                      requested=requested)
                )

    @api.model
    def _get_qty_for_mode(self, product, mode):
        if mode == "on_hand":
            return product.qty_available
        if mode == "forecasted":
            return product.virtual_available
        return product.free_qty
