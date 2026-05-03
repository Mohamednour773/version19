from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_is_zero


class StockRequest(models.Model):
    _name = 'stock.request'
    _description = 'Inter-Branch Stock Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(
        string='Request Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
        tracking=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    request_location_id = fields.Many2one(
        'stock.location',
        string='Requesting Branch Location',
        required=True,
        domain="[('usage', '=', 'internal')]",
        tracking=True,
    )
    scheduled_date = fields.Datetime(
        string='Required Date',
        required=True,
        default=fields.Datetime.now,
        tracking=True,
    )
    sale_order_id = fields.Many2one(
        'sale.order',
        string='Sales Order',
        tracking=True,
    )
    source_document = fields.Char(
        string='Source Document',
        tracking=True,
        copy=False,
    )
    route_id = fields.Many2one(
        'stock.route',
        string='Supply Route',
        compute='_compute_route_id',
        inverse='_inverse_route_id',
        store=True,
        readonly=False,
        tracking=True,
    )
    destination_warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Destination Warehouse',
        compute='_compute_warehouse_data',
        store=True,
        readonly=True,
    )
    source_location_id = fields.Many2one(
        'stock.location',
        string='Source Location',
        compute='_compute_warehouse_data',
        store=True,
        readonly=True,
    )
    source_warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Source Warehouse',
        compute='_compute_warehouse_data',
        store=True,
        readonly=True,
    )
    line_ids = fields.One2many(
        'stock.request.line',
        'request_id',
        string='Request Lines',
        copy=True,
    )
    picking_ids = fields.One2many(
        'stock.picking',
        'stock_request_id',
        string='Pickings',
        readonly=True,
    )
    request_picking_ids = fields.One2many(
        'stock.picking',
        'stock_request_id',
        string='Operational Pickings',
        compute='_compute_picking_groups',
    )
    return_picking_ids = fields.One2many(
        'stock.picking',
        'stock_request_id',
        string='Return Pickings',
        compute='_compute_picking_groups',
    )
    picking_count = fields.Integer(
        string='Pickings',
        compute='_compute_counts',
    )
    return_picking_count = fields.Integer(
        string='Returns',
        compute='_compute_counts',
    )
    has_pending_return = fields.Boolean(
        string='Has Pending Return',
        compute='_compute_return_status',
        store=True,
    )
    return_state = fields.Selection(
        [
            ('no_return', 'No Return'),
            ('partial_return', 'Partial Return'),
            ('fully_returned', 'Fully Returned'),
        ],
        string='Return Status',
        compute='_compute_return_status',
        store=True,
    )
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
            ('in_progress', 'In Progress'),
            ('partial', 'Partial'),
            ('done', 'Done'),
            ('cancel', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        tracking=True,
        copy=False,
    )

    @api.depends('request_location_id', 'line_ids.route_id')
    def _compute_route_id(self):
        for request in self:
            route = request.line_ids.filtered('show_route_info')[:1].route_id
            if not route:
                route = request._get_route_from_location()
            request.route_id = route

    def _inverse_route_id(self):
        return

    @api.depends('request_location_id', 'route_id')
    def _compute_warehouse_data(self):
        for request in self:
            destination_warehouse = request._get_destination_warehouse()
            source_location = request._get_source_location_from_route()
            source_warehouse = False
            if source_location:
                source_warehouse = request._find_warehouse_from_location(source_location)
            request.destination_warehouse_id = destination_warehouse
            request.source_location_id = source_location
            request.source_warehouse_id = source_warehouse

    @api.depends('picking_ids.stock_request_kind')
    def _compute_picking_groups(self):
        for request in self:
            request.request_picking_ids = request.picking_ids.filtered(
                lambda picking: picking.stock_request_kind in ('request_out', 'request_in')
            )
            request.return_picking_ids = request.picking_ids.filtered(
                lambda picking: picking.stock_request_kind in ('return_out', 'return_in')
            )

    @api.depends('picking_ids.stock_request_kind')
    def _compute_counts(self):
        for request in self:
            request.picking_count = len(
                request.picking_ids.filtered(
                    lambda picking: picking.stock_request_kind in ('request_out', 'request_in')
                )
            )
            request.return_picking_count = len(
                request.picking_ids.filtered(
                    lambda picking: picking.stock_request_kind in ('return_out', 'return_in')
                )
            )

    @api.depends('line_ids.qty_done', 'line_ids.qty_returned')
    def _compute_return_status(self):
        for request in self:
            total_dispatched = sum(request.line_ids.mapped('qty_done'))
            total_returned = sum(request.line_ids.mapped('qty_returned'))
            has_pending = any(line.available_return_qty > 0 for line in request.line_ids)
            request.has_pending_return = has_pending
            if float_is_zero(total_dispatched, precision_rounding=0.00001):
                request.return_state = 'no_return'
            elif float_compare(total_returned, total_dispatched, precision_rounding=0.00001) >= 0:
                request.return_state = 'fully_returned'
            elif float_is_zero(total_returned, precision_rounding=0.00001):
                request.return_state = 'no_return'
            else:
                request.return_state = 'partial_return'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('stock.request') or _('New')
            if vals.get('sale_order_id') and not vals.get('source_document'):
                sale_order = self.env['sale.order'].browse(vals['sale_order_id'])
                vals['source_document'] = sale_order.name
        return super().create(vals_list)

    @api.onchange('sale_order_id')
    def _onchange_sale_order_id(self):
        for request in self:
            if request.sale_order_id:
                request.source_document = request.sale_order_id.name

    @api.constrains('request_location_id')
    def _check_request_location_id(self):
        for request in self:
            if request.request_location_id and request.request_location_id.usage != 'internal':
                raise ValidationError(_('The requesting branch location must be an internal location.'))

    @api.constrains('line_ids')
    def _check_line_ids(self):
        for request in self:
            if request.state != 'draft' and not request.line_ids:
                raise ValidationError(_('At least one request line is required.'))

    def unlink(self):
        for request in self:
            if request.state != 'draft':
                raise UserError(_('Only draft requests can be deleted.'))
        return super().unlink()

    def action_confirm(self):
        for request in self:
            request._validate_before_confirm()
            request._create_initial_pickings()
            request.state = 'confirmed'
        return True

    def action_cancel(self):
        for request in self:
            open_pickings = request.picking_ids.filtered(lambda picking: picking.state not in ('done', 'cancel'))
            open_pickings.action_cancel()
            request.state = 'cancel'
        return True

    def action_reset_to_draft(self):
        for request in self:
            if request.picking_ids.filtered(lambda picking: picking.state not in ('cancel',)):
                raise UserError(_('Cancel all linked pickings before resetting the request to draft.'))
            request.state = 'draft'
        return True

    def action_view_pickings(self):
        self.ensure_one()
        action = self.env.ref('stock.action_picking_tree_all').read()[0]
        action['domain'] = [('id', 'in', self.request_picking_ids.ids)]
        action['context'] = {'default_stock_request_id': self.id}
        return action

    def action_view_returns(self):
        self.ensure_one()
        action = self.env.ref('stock.action_picking_tree_all').read()[0]
        action['domain'] = [('id', 'in', self.return_picking_ids.ids)]
        action['context'] = {'default_stock_request_id': self.id}
        return action

    def action_open_return_wizard(self):
        self.ensure_one()
        if not self.has_pending_return:
            raise UserError(_('There is no dispatched quantity available for return.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Create Return'),
            'res_model': 'stock.request.return.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_request_id': self.id},
        }

    def _validate_before_confirm(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Only draft requests can be confirmed.'))
        if not self.line_ids:
            raise UserError(_('Add at least one product line before confirming the request.'))
        if not self.route_id:
            raise UserError(_('No supply route could be determined for this request.'))
        if not self.source_location_id:
            raise UserError(_('The selected route does not resolve to a source location.'))
        if self.source_location_id == self.request_location_id:
            raise UserError(_('The source location and requesting location must be different.'))
        for line in self.line_ids:
            if float_compare(line.qty_requested, 0.0, precision_rounding=line.product_uom_id.rounding) <= 0:
                raise UserError(_('Requested quantities must be greater than zero.'))

    def _get_destination_warehouse(self):
        self.ensure_one()
        if not self.request_location_id:
            return self.env['stock.warehouse']
        return self._find_warehouse_from_location(self.request_location_id)

    def _find_warehouse_from_location(self, location):
        self.ensure_one()
        if not location:
            return self.env['stock.warehouse']
        warehouses = self.env['stock.warehouse'].search([])
        direct_match = warehouses.filtered(lambda warehouse: warehouse.lot_stock_id == location)[:1]
        if direct_match:
            return direct_match
        for warehouse in warehouses:
            child_locations = self.env['stock.location'].search(
                [('id', 'child_of', warehouse.view_location_id.id)]
            )
            if location in child_locations:
                return warehouse
        return self.env['stock.warehouse']

    def _get_route_from_location(self):
        self.ensure_one()
        warehouse = self._get_destination_warehouse()
        if not warehouse:
            return self.env['stock.route']
        route = warehouse.route_ids.filtered(
            lambda route_item: 'supply' in (route_item.name or '').lower()
        )[:1]
        if route:
            return route
        return self.env['stock.route'].search(
            [('name', 'ilike', warehouse.name), ('name', 'ilike', 'Supply Product From')],
            limit=1,
        )

    def _get_source_location_from_route(self):
        self.ensure_one()
        outgoing_rule, _incoming_rule = self._get_request_route_rules()
        return outgoing_rule.location_src_id if outgoing_rule else self.env['stock.location']

    def _get_route_locations(self, location):
        self.ensure_one()
        if not location:
            return self.env['stock.location']
        return self.env['stock.location'].search([('id', 'child_of', location.id)])

    def _get_request_route_rules(self):
        self.ensure_one()
        route = self.route_id or self._get_route_from_location()
        if not route or not route.rule_ids:
            return self.env['stock.rule'], self.env['stock.rule']

        destination_locations = self._get_route_locations(self.request_location_id)
        incoming_rule = route.rule_ids.filtered(
            lambda rule: rule.location_dest_id and rule.location_dest_id in destination_locations
        )[:1]
        if not incoming_rule:
            incoming_rule = route.rule_ids.filtered(lambda rule: rule.location_dest_id == self.request_location_id)[:1]
        if not incoming_rule:
            incoming_rule = route.rule_ids.sorted(lambda rule: rule.sequence)[-1:]

        outgoing_rule = self.env['stock.rule']
        if incoming_rule:
            bridge_locations = self._get_route_locations(incoming_rule.location_src_id)
            outgoing_rule = route.rule_ids.filtered(
                lambda rule: rule != incoming_rule
                and rule.location_dest_id
                and rule.location_dest_id in bridge_locations
            )[:1]
        if not outgoing_rule:
            outgoing_rule = route.rule_ids.filtered(lambda rule: rule != incoming_rule)[:1]
        if not outgoing_rule:
            outgoing_rule = incoming_rule
        return outgoing_rule, incoming_rule

    def _get_return_route_rules(self):
        self.ensure_one()
        outgoing_picking = self.request_picking_ids.filtered(lambda picking: picking.stock_request_kind == 'request_out')[:1]
        incoming_picking = self.request_picking_ids.filtered(lambda picking: picking.stock_request_kind == 'request_in')[:1]
        return outgoing_picking, incoming_picking

    def _get_rule_picking_type(self, rule, fallback_warehouse=False, fallback_code=False):
        self.ensure_one()
        if rule and rule.picking_type_id:
            return rule.picking_type_id
        if fallback_warehouse and fallback_code:
            picking_type = self.env['stock.picking.type'].search(
                [('warehouse_id', '=', fallback_warehouse.id), ('code', '=', fallback_code)],
                limit=1,
            )
            if picking_type:
                return picking_type
        raise UserError(_('The selected route does not define a picking type for this transfer step.'))

    def _prepare_picking_vals(self, kind, picking_type, location_id, location_dest_id, counterpart=None):
        self.ensure_one()
        origin = self.name
        if self.source_document:
            origin = '%s - %s' % (self.name, self.source_document)
        return {
            'picking_type_id': picking_type.id,
            'location_id': location_id.id,
            'location_dest_id': location_dest_id.id,
            'scheduled_date': self.scheduled_date,
            'origin': origin,
            'company_id': self.company_id.id,
            'stock_request_id': self.id,
            'stock_request_kind': kind,
            'counterpart_picking_id': counterpart.id if counterpart else False,
        }

    def _prepare_move_vals(self, line, picking, quantity, counterpart_move=None):
        self.ensure_one()
        return {
            'picking_id': picking.id,
            'product_id': line.product_id.id,
            'product_uom': line.product_uom_id.id,
            'product_uom_qty': quantity,
            'location_id': picking.location_id.id,
            'location_dest_id': picking.location_dest_id.id,
            'company_id': self.company_id.id,
            'description_picking': line.note or line.product_id.display_name,
            'stock_request_line_id': line.id,
            'counterpart_move_id': counterpart_move.id if counterpart_move else False,
        }

    def _create_initial_pickings(self):
        for request in self:
            if request.request_picking_ids:
                raise UserError(_('Operational pickings already exist for this request.'))
            outgoing_rule, incoming_rule = request._get_request_route_rules()
            if not outgoing_rule or not incoming_rule:
                raise UserError(_('No valid stock rules were found on the selected route.'))
            outgoing_type = request._get_rule_picking_type(
                outgoing_rule,
                fallback_warehouse=request.source_warehouse_id,
                fallback_code='outgoing',
            )
            incoming_type = request._get_rule_picking_type(
                incoming_rule,
                fallback_warehouse=request.destination_warehouse_id,
                fallback_code='incoming',
            )
            outgoing_picking = self.env['stock.picking'].create(
                request._prepare_picking_vals(
                    'request_out',
                    outgoing_type,
                    outgoing_rule.location_src_id,
                    outgoing_rule.location_dest_id,
                )
            )
            incoming_picking = self.env['stock.picking'].create(
                request._prepare_picking_vals(
                    'request_in',
                    incoming_type,
                    incoming_rule.location_src_id,
                    incoming_rule.location_dest_id,
                    counterpart=outgoing_picking,
                )
            )
            outgoing_picking.counterpart_picking_id = incoming_picking.id
            for line in request.line_ids:
                outgoing_move = self.env['stock.move'].create(
                    request._prepare_move_vals(line, outgoing_picking, line.qty_requested)
                )
                incoming_move = self.env['stock.move'].create(
                    request._prepare_move_vals(
                        line,
                        incoming_picking,
                        line.qty_requested,
                        counterpart_move=outgoing_move,
                    )
                )
                outgoing_move.counterpart_move_id = incoming_move.id
                incoming_move.write({'move_orig_ids': [(4, outgoing_move.id)]})
            (outgoing_picking | incoming_picking).action_confirm()

    def _create_receipt_backorder_from_dispatch(self, outgoing_backorder):
        self.ensure_one()
        if outgoing_backorder.counterpart_picking_id:
            return outgoing_backorder.counterpart_picking_id
        _outgoing_rule, incoming_rule = self._get_request_route_rules()
        incoming_type = self._get_rule_picking_type(
            incoming_rule,
            fallback_warehouse=self.destination_warehouse_id,
            fallback_code='incoming',
        )
        incoming_backorder = self.env['stock.picking'].create(
            self._prepare_picking_vals(
                'request_in',
                incoming_type,
                incoming_rule.location_src_id,
                incoming_rule.location_dest_id,
                counterpart=outgoing_backorder,
            )
        )
        outgoing_backorder.counterpart_picking_id = incoming_backorder.id
        for move in outgoing_backorder.move_ids.filtered(lambda move_item: move_item.state not in ('cancel', 'done')):
            incoming_move = self.env['stock.move'].create(
                self._prepare_move_vals(
                    move.stock_request_line_id,
                    incoming_backorder,
                    move.product_uom_qty,
                    counterpart_move=move,
                )
            )
            move.counterpart_move_id = incoming_move.id
            incoming_move.write({'move_orig_ids': [(4, move.id)]})
        incoming_backorder.action_confirm()
        return incoming_backorder

    def _recompute_state(self):
        for request in self:
            if request.state == 'cancel':
                continue
            if not request.request_picking_ids:
                request.state = 'draft'
                continue
            all_requested = all(
                float_compare(
                    line.qty_received,
                    line.qty_requested,
                    precision_rounding=line.product_uom_id.rounding,
                ) >= 0
                and float_compare(
                    line.qty_done,
                    line.qty_requested,
                    precision_rounding=line.product_uom_id.rounding,
                ) >= 0
                for line in request.line_ids
            )
            any_received = any(
                not float_is_zero(line.qty_received, precision_rounding=line.product_uom_id.rounding)
                for line in request.line_ids
            )
            any_dispatched = any(
                not float_is_zero(line.qty_done, precision_rounding=line.product_uom_id.rounding)
                for line in request.line_ids
            )
            all_dispatched = all(
                float_compare(
                    line.qty_done,
                    line.qty_requested,
                    precision_rounding=line.product_uom_id.rounding,
                ) >= 0
                for line in request.line_ids
            )
            if all_requested:
                request.state = 'done'
            elif any_received or any_dispatched:
                request.state = 'in_progress' if all_dispatched else 'partial'
            else:
                request.state = 'confirmed'


class StockRequestLine(models.Model):
    _name = 'stock.request.line'
    _description = 'Inter-Branch Stock Request Line'
    _order = 'id'

    request_id = fields.Many2one(
        'stock.request',
        string='Request',
        required=True,
        ondelete='cascade',
        index=True,
    )
    company_id = fields.Many2one(
        'res.company',
        related='request_id.company_id',
        store=True,
        readonly=True,
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        domain=[],
    )
    product_uom_id = fields.Many2one(
        'uom.uom',
        string='Unit of Measure',
        required=True,
    )
    qty_requested = fields.Float(
        string='Requested Quantity',
        required=True,
        digits='Product Unit of Measure',
        default=1.0,
    )
    qty_done = fields.Float(
        string='Dispatched Quantity',
        compute='_compute_quantities',
        store=True,
        digits='Product Unit of Measure',
    )
    qty_received = fields.Float(
        string='Received Quantity',
        compute='_compute_quantities',
        store=True,
        digits='Product Unit of Measure',
    )
    qty_returned = fields.Float(
        string='Returned Quantity',
        compute='_compute_quantities',
        store=True,
        digits='Product Unit of Measure',
    )
    available_return_qty = fields.Float(
        string='Available to Return',
        compute='_compute_quantities',
        store=True,
        digits='Product Unit of Measure',
    )
    note = fields.Text(string='Note')
    route_id = fields.Many2one(
        'stock.route',
        string='Product Route',
        compute='_compute_route_data',
        store=True,
    )
    show_route_info = fields.Boolean(
        string='Show Route',
        compute='_compute_route_data',
        store=True,
    )
    move_ids = fields.One2many(
        'stock.move',
        'stock_request_line_id',
        string='Moves',
        readonly=True,
    )

    @api.depends(
        'product_id',
        'product_id.route_ids',
        'product_id.categ_id.total_route_ids',
        'product_id.categ_id.route_ids',
    )
    def _compute_route_data(self):
        for line in self:
            route = line.product_id.route_ids[:1]
            if not route:
                route = line.product_id.categ_id.total_route_ids[:1] or line.product_id.categ_id.route_ids[:1]
            line.route_id = route
            line.show_route_info = bool(route)

    @api.depends(
        'move_ids.state',
        'move_ids.quantity',
        'move_ids.stock_request_line_id',
        'move_ids.picking_id.stock_request_kind',
    )
    def _compute_quantities(self):
        for line in self:
            dispatched = 0.0
            received = 0.0
            returned = 0.0
            for move in line.move_ids.filtered(lambda move_item: move_item.state == 'done'):
                if move.stock_request_line_id != line:
                    continue
                if move.picking_id.stock_request_kind == 'request_out':
                    dispatched += move.quantity
                elif move.picking_id.stock_request_kind == 'request_in':
                    received += move.quantity
                elif move.picking_id.stock_request_kind == 'return_out':
                    returned += move.quantity
            line.qty_done = dispatched
            line.qty_received = received
            line.qty_returned = returned
            line.available_return_qty = max(dispatched - returned, 0.0)

    @api.onchange('product_id')
    def _onchange_product_id(self):
        for line in self:
            if line.product_id:
                line.product_uom_id = line.product_id.uom_id

    @api.constrains('qty_requested')
    def _check_qty_requested(self):
        for line in self:
            if float_compare(line.qty_requested, 0.0, precision_rounding=line.product_uom_id.rounding) <= 0:
                raise ValidationError(_('Requested quantity must be greater than zero.'))
