from odoo import models


class MrpBom(models.Model):
    _inherit = ["mrp.bom", "universal.approval.mixin"]
