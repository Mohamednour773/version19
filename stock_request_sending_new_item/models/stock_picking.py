from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    stock_request_sending_id = fields.Many2one('stock.request.sending', string='Stock Request Sending', readonly=True)
    stock_request_step = fields.Selection([
        ('picking_1', 'Step 1: Outgoing'),
        ('picking_2', 'Step 2: Incoming'),
    ], string='Stock Request Step', readonly=True)

class StockMove(models.Model):
    _inherit = 'stock.move'

    stock_request_sending_line_id = fields.Many2one('stock.request.sending.line', string='Stock Request Line', readonly=True)
    first_picking_move_id = fields.Many2one('stock.move', string='First Picking Move', readonly=True)

    @api.constrains('quantity')
    def _check_quantity_done_limit(self):
        for move in self:
            if move.first_picking_move_id:
                # This is a move in the second picking
                first_move = move.first_picking_move_id
                if move.quantity > first_move.quantity:
                    raise ValidationError(_(
                        "You cannot receive more quantity than what was dispatched in the first step.\n"
                        "Product: %s\n"
                        "Dispatched Quantity: %s\n"
                        "Trying to Receive: %s"
                    ) % (move.product_id.display_name, first_move.quantity, move.quantity))
