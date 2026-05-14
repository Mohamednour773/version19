from odoo import api, fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    prevent_negative_stock = fields.Boolean(
        string="Prevent Negative Stock",
        default=False,
        help="When enabled, blocks POS sales that would result in negative stock.",
    )
    negative_stock_check_mode = fields.Selection(
        selection=[
            ("on_hand", "On Hand"),
            ("available", "Available"),
            ("forecasted", "Forecasted"),
        ],
        string="Stock Check Mode",
        default="available",
        help="Which quantity metric to check against.\n"
             "On Hand: Physical stock in warehouse.\n"
             "Available: On hand minus reserved.\n"
             "Forecasted: Available plus incoming minus outgoing.",
    )
    allow_manager_override = fields.Boolean(
        string="Allow Manager Override",
        default=True,
        help="Allow managers to override the negative stock block via PIN.",
    )
    override_user_group_id = fields.Many2one(
        comodel_name="res.groups",
        string="Override Group",
        help="User group allowed to perform the override. "
             "Defaults to POS Manager if left empty.",
    )
    excluded_product_categ_ids = fields.Many2many(
        comodel_name="product.category",
        relation="pos_config_excluded_categ_rel",
        column1="config_id",
        column2="categ_id",
        string="Excluded Categories",
        help="Product categories exempt from the negative stock check (e.g., services).",
    )
    excluded_product_ids = fields.Many2many(
        comodel_name="product.product",
        relation="pos_config_excluded_product_rel",
        column1="config_id",
        column2="product_id",
        string="Excluded Products",
        help="Specific products exempt from the negative stock check.",
    )
    block_unstorable_products = fields.Boolean(
        string="Block Unstorable Products",
        default=False,
        help="Apply the negative stock check to consumable and service products as well.",
    )
    refresh_stock_interval = fields.Integer(
        string="Stock Refresh Interval (s)",
        default=60,
        help="Seconds between automatic background stock refresh from the server.",
    )
    require_override_reason = fields.Boolean(
        string="Require Override Reason",
        default=False,
        help="When enabled, managers must provide a reason text for each override.",
    )
