from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare


class StockRequestReturnWizard(models.TransientModel):
    _name = 'stock.request.return.wizard'
    _description = 'Stock Request Return Wizard'

    request_id = fields.Many2one(
        'stock.request',
        string='Stock Request',
        required=True,
        readonly=True,
    )
    reason = fields.Text(string='Reason', required=True)
    line_ids = fields.One2many(
        'stock.request.return.wizard.line',
        'wizard_id',
        string='Return Lines',
    )

    @api.model
    def default_get(self, fields_list):
        result = super().default_get(fields_list)
        request = self.env['stock.request'].browse(
            self.env.context.get('default_request_id') or self.env.context.get('active_id')
        )
        if request:
            result['request_id'] = request.id
            result['line_ids'] = [
                (
                    0,
                    0,
                    {
                        'request_line_id': line.id,
                        'product_id': line.product_id.id,
                        'product_uom_id': line.product_uom_id.id,
                        'qty_available_return': line.available_return_qty,
                        'qty_to_return': line.available_return_qty,
                        'note': line.note,
                    },
                )
                for line in request.line_ids
                if float_compare(line.available_return_qty, 0.0, precision_rounding=line.product_uom_id.rounding) > 0
            ]
        return result

    def action_create_return(self):
        self.ensure_one()
        request = self.request_id
        if not self.line_ids:
            raise UserError(_('There is nothing available to return.'))
        valid_lines = self.line_ids.filtered(
            lambda line: float_compare(line.qty_to_return, 0.0, precision_rounding=line.product_uom_id.rounding) > 0
        )
        if not valid_lines:
            raise UserError(_('Enter at least one quantity to return.'))

        original_outgoing, original_incoming = request._get_return_route_rules()
        if not original_outgoing or not original_incoming:
            raise UserError(_('The request must have linked operational pickings before you can create returns.'))

        return_out = self.env['stock.picking'].create({
            **request._prepare_picking_vals(
                'return_out',
                original_incoming.picking_type_id,
                original_incoming.location_dest_id,
                original_incoming.location_id,
            ),
            'origin': '%s - Return' % request.name,
        })
        return_in = self.env['stock.picking'].create({
            **request._prepare_picking_vals(
                'return_in',
                original_outgoing.picking_type_id,
                original_outgoing.location_dest_id,
                original_outgoing.location_id,
                counterpart=return_out,
            ),
            'origin': '%s - Return' % request.name,
        })
        return_out.counterpart_picking_id = return_in.id

        for wizard_line in valid_lines:
            wizard_line._validate_qty_to_return()
            return_out_move = self.env['stock.move'].create({
                **request._prepare_move_vals(
                    wizard_line.request_line_id,
                    return_out,
                    wizard_line.qty_to_return,
                ),
                'description_picking': self.reason,
            })
            return_in_move = self.env['stock.move'].create({
                **request._prepare_move_vals(
                    wizard_line.request_line_id,
                    return_in,
                    wizard_line.qty_to_return,
                    counterpart_move=return_out_move,
                ),
                'description_picking': self.reason,
            })
            return_out_move.counterpart_move_id = return_in_move.id
            return_in_move.write({'move_orig_ids': [(4, return_out_move.id)]})

        (return_out | return_in).action_confirm()
        request._recompute_state()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Return Picking'),
            'res_model': 'stock.picking',
            'res_id': return_out.id,
            'view_mode': 'form',
            'target': 'current',
        }


class StockRequestReturnWizardLine(models.TransientModel):
    _name = 'stock.request.return.wizard.line'
    _description = 'Stock Request Return Wizard Line'

    wizard_id = fields.Many2one(
        'stock.request.return.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade',
    )
    request_line_id = fields.Many2one(
        'stock.request.line',
        string='Request Line',
        required=True,
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
    )
    product_uom_id = fields.Many2one(
        'uom.uom',
        string='Unit of Measure',
    )
    qty_available_return = fields.Float(
        string='Available to Return',
        digits='Product Unit of Measure',
    )
    qty_to_return = fields.Float(
        string='Quantity to Return',
        digits='Product Unit of Measure',
    )
    note = fields.Text(string='Original Note')

    def _validate_qty_to_return(self):
        self.ensure_one()
        if float_compare(self.qty_to_return, 0.0, precision_rounding=self.product_uom_id.rounding) <= 0:
            raise UserError(_('Return quantities must be greater than zero.'))
        if float_compare(
            self.qty_to_return,
            self.qty_available_return,
            precision_rounding=self.product_uom_id.rounding,
        ) > 0:
            raise UserError(
                _('You cannot return more than the dispatched quantity available for %s.')
                % self.product_id.display_name
            )
