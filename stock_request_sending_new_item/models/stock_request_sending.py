from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class StockRequestSending(models.Model):
    _name = 'stock.request.sending'
    _description = 'Stock Request Sending'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(
        string='Reference', 
        required=True, 
        copy=False, 
        readonly=True, 
        index=True, 
        default=lambda self: _('New')
    )
    source_warehouse_id = fields.Many2one(
        'stock.warehouse', 
        string='Source Warehouse', 
        required=True, 
        tracking=True
    )
    destination_warehouse_id = fields.Many2one(
        'stock.warehouse', 
        string='Destination Warehouse', 
        required=True, 
        tracking=True
    )
    line_ids = fields.One2many(
        'stock.request.sending.line', 
        'request_id', 
        string='Lines', 
        copy=True
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)
    
    company_id = fields.Many2one(
        'res.company', 
        string='Company', 
        default=lambda self: self.env.company, 
        required=True
    )
    
    picking_ids = fields.One2many(
        'stock.picking', 
        'stock_request_sending_id', 
        string='Pickings'
    )
    picking_count = fields.Integer(
        string='Picking Count', 
        compute='_compute_picking_count'
    )

    @api.depends('picking_ids')
    def _compute_picking_count(self):
        for record in self:
            record.picking_count = len(record.picking_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('stock.request.sending') or _('New')
        return super().create(vals_list)

    def action_confirm(self):
        for record in self:
            if not record.line_ids:
                raise UserError(_("Please add at least one line before confirming."))
            if record.source_warehouse_id == record.destination_warehouse_id:
                raise UserError(_("Source and Destination warehouses cannot be the same."))
            
            record._create_pickings()
            record.state = 'confirmed'

    def _create_pickings(self):
        self.ensure_one()
        transit_location = self.company_id.internal_transit_location_id
        if not transit_location:
            # Fallback to search if not set on company
            transit_location = self.env['stock.location'].search([
                ('usage', '=', 'transit'),
                ('company_id', '=', self.company_id.id)
            ], limit=1)
        
        if not transit_location:
            raise UserError(_("No transit location found for this company. Please configure one."))

        # Picking 1: Source -> Transit
        picking_type_out = self.source_warehouse_id.out_type_id
        picking_1_vals = self._prepare_picking_vals(
            picking_type_out,
            self.source_warehouse_id.lot_stock_id,
            transit_location,
            'picking_1'
        )
        picking_1 = self.env['stock.picking'].create(picking_1_vals)

        # Picking 2: Transit -> Destination
        picking_type_in = self.destination_warehouse_id.in_type_id
        picking_2_vals = self._prepare_picking_vals(
            picking_type_in,
            transit_location,
            self.destination_warehouse_id.lot_stock_id,
            'picking_2'
        )
        picking_2 = self.env['stock.picking'].create(picking_2_vals)

        for line in self.line_ids:
            # Move 1
            move_1_vals = line._prepare_move_vals(picking_1, self.source_warehouse_id.lot_stock_id, transit_location)
            move_1 = self.env['stock.move'].create(move_1_vals)
            
            # Move 2
            move_2_vals = line._prepare_move_vals(picking_2, transit_location, self.destination_warehouse_id.lot_stock_id)
            move_2 = self.env['stock.move'].create(move_2_vals)
            
            # Link moves for validation logic
            move_2.first_picking_move_id = move_1.id

        picking_1.action_confirm()
        picking_1.action_assign()
        picking_2.action_confirm()
        picking_2.action_assign()

    def _prepare_picking_vals(self, picking_type, src_loc, dest_loc, step_type):
        return {
            'picking_type_id': picking_type.id,
            'location_id': src_loc.id,
            'location_dest_id': dest_loc.id,
            'origin': self.name,
            'stock_request_sending_id': self.id,
            'stock_request_step': step_type,
            'company_id': self.company_id.id,
        }

    def action_view_pickings(self):
        self.ensure_one()
        action = self.env.ref('stock.action_picking_tree_all').read()[0]
        action['domain'] = [('stock_request_sending_id', '=', self.id)]
        action['context'] = {'default_stock_request_sending_id': self.id}
        return action

    def action_cancel(self):
        for record in self:
            for picking in record.picking_ids:
                if picking.state not in ('done', 'cancel'):
                    picking.action_cancel()
            record.state = 'cancel'

class StockRequestSendingLine(models.Model):
    _name = 'stock.request.sending.line'
    _description = 'Stock Request Sending Line'

    request_id = fields.Many2one('stock.request.sending', string='Request', ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product', required=True)
    quantity = fields.Float(string='Quantity', required=True, default=1.0)
    uom_id = fields.Many2one(
        'uom.uom', 
        string='Unit of Measure', 
        required=True,
        compute='_compute_uom_id',
        store=True,
        readonly=False,
        precompute=True
    )
    note = fields.Text(string='Note')

    @api.depends('product_id')
    def _compute_uom_id(self):
        for line in self:
            if line.product_id:
                line.uom_id = line.product_id.uom_id
            else:
                line.uom_id = False

    def _prepare_move_vals(self, picking, src_loc, dest_loc):
        return {
            'description_picking': self.product_id.display_name,
            'product_id': self.product_id.id,
            'product_uom_qty': self.quantity,
            'product_uom': self.uom_id.id,
            'location_id': src_loc.id,
            'location_dest_id': dest_loc.id,
            'picking_id': picking.id,
            'stock_request_sending_line_id': self.id,
            'company_id': picking.company_id.id,
        }
