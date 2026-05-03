from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_is_zero


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    stock_request_id = fields.Many2one(
        'stock.request',
        string='Stock Request',
        copy=False,
        index=True,
    )
    stock_request_kind = fields.Selection(
        [
            ('request_out', 'Request Dispatch'),
            ('request_in', 'Request Receipt'),
            ('return_out', 'Return Dispatch'),
            ('return_in', 'Return Receipt'),
        ],
        string='Stock Request Flow',
        copy=False,
        index=True,
    )
    counterpart_picking_id = fields.Many2one(
        'stock.picking',
        string='Counterpart Picking',
        copy=False,
        index=True,
    )

    def _action_done(self):
        result = super()._action_done()
        request_pickings = self.filtered('stock_request_id')
        for picking in request_pickings:
            picking._validate_counterpart_quantities()
        for picking in request_pickings:
            if picking.stock_request_kind == 'request_out':
                picking._sync_request_dispatch()
            elif picking.stock_request_kind == 'request_in':
                picking._sync_request_receipt()
            elif picking.stock_request_kind == 'return_out':
                picking._sync_return_dispatch()
            elif picking.stock_request_kind == 'return_in':
                picking.stock_request_id._recompute_state()
        return result

    def _validate_counterpart_quantities(self):
        for picking in self.filtered(lambda record: record.stock_request_kind in ('request_in', 'return_in')):
            for move in picking.move_ids.filtered(lambda move_item: move_item.state == 'done'):
                counterpart_move = move.counterpart_move_id
                if not counterpart_move:
                    continue
                allowed_qty = counterpart_move.quantity
                if float_compare(move.quantity, allowed_qty, precision_rounding=move.product_uom.rounding) > 0:
                    raise UserError(
                        _(
                            'You cannot validate %s with %s %s because only %s %s were dispatched on the counterpart transfer.'
                        )
                        % (
                            move.product_id.display_name,
                            move.quantity,
                            move.product_uom.name,
                            allowed_qty,
                            move.product_uom.name,
                        )
                    )

    def _sync_request_dispatch(self):
        self.ensure_one()
        request = self.stock_request_id
        counterpart = self.counterpart_picking_id
        if not counterpart:
            counterpart = request._create_receipt_backorder_from_dispatch(self)
        for move in self.move_ids.filtered(lambda move_item: move_item.state == 'done'):
            if move.counterpart_move_id:
                move.counterpart_move_id.write({'product_uom_qty': move.quantity})
        if counterpart.state == 'draft':
            counterpart.action_confirm()
        backorders = self.backorder_ids.filtered(
            lambda picking: picking.stock_request_id == request and picking.stock_request_kind == 'request_out'
        )
        for backorder in backorders:
            request._create_receipt_backorder_from_dispatch(backorder)
        request._recompute_state()

    def _sync_request_receipt(self):
        self.ensure_one()
        self.stock_request_id._recompute_state()

    def _sync_return_dispatch(self):
        self.ensure_one()
        request = self.stock_request_id
        counterpart = self.counterpart_picking_id
        if not counterpart:
            raise UserError(_('The return dispatch has no linked return receipt.'))
        for move in self.move_ids.filtered(lambda move_item: move_item.state == 'done'):
            if move.counterpart_move_id:
                move.counterpart_move_id.write({'product_uom_qty': move.quantity})
        if counterpart.state == 'draft':
            counterpart.action_confirm()
        request._recompute_state()
