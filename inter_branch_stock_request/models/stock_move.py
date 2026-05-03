from odoo import fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    stock_request_line_id = fields.Many2one(
        'stock.request.line',
        string='Stock Request Line',
        copy=False,
        index=True,
    )
    counterpart_move_id = fields.Many2one(
        'stock.move',
        string='Counterpart Move',
        copy=False,
        index=True,
    )
