# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError


class ClubTrainer(models.Model):
    _name = 'club.trainer'
    _description = 'Club Trainer'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char(string='Trainer Name', required=True, tracking=True)
    code = fields.Char(string='Trainer Code', copy=False, readonly=True, default='New')
    active = fields.Boolean(default=True, tracking=True)

    # Personal info
    partner_id = fields.Many2one(
        'res.partner',
        string='Contact',
        required=True,
        ondelete='restrict',
    )
    user_id = fields.Many2one('res.users', string='Related User')
    phone = fields.Char(related='partner_id.phone', string='Phone', store=True)
    email = fields.Char(related='partner_id.email', string='Email', store=True)
    image_1920 = fields.Image(related='partner_id.image_1920', string='Photo')

    # Branch
    branch_id = fields.Many2one(
        'club.branch',
        string='Branch',
        required=True,
        tracking=True,
        ondelete='restrict',
    )

    # Specializations
    specialization = fields.Selection([
        ('swimming', 'Swimming'),
        ('fitness', 'Fitness'),
        ('football', 'Football'),
        ('tennis', 'Tennis'),
        ('martial_arts', 'Martial Arts'),
        ('yoga', 'Yoga'),
        ('other', 'Other'),
    ], string='Specialization', required=True, default='swimming')

    # Commission
    commission_pct = fields.Float(
        string='Commission %',
        default=35.0,
        digits=(5, 2),
        tracking=True,
    )

    # Employment
    employee_type = fields.Selection([
        ('full_time', 'Full Time'),
        ('part_time', 'Part Time'),
        ('freelance', 'Freelance'),
    ], string='Employment Type', default='full_time')

    hire_date = fields.Date(string='Hire Date')
    notes = fields.Text(string='Notes')

    # Relations
    class_ids = fields.One2many('club.class', 'trainer_id', string='Classes')
    session_ids = fields.One2many('club.session', 'trainer_id', string='Sessions')
    commission_ids = fields.One2many('club.trainer.commission', 'trainer_id', string='Commissions')

    # Computed
    class_count = fields.Integer(compute='_compute_counts', string='Classes')
    session_count = fields.Integer(compute='_compute_counts', string='Sessions')
    total_commission = fields.Float(
        compute='_compute_total_commission',
        string='Total Commission',
        digits=(16, 2),
    )
    pending_commission = fields.Float(
        compute='_compute_total_commission',
        string='Pending Commission',
        digits=(16, 2),
    )

    _sql_constraints = [
        ('commission_pct_range', 'CHECK(commission_pct >= 0 AND commission_pct <= 100)',
         'Commission percentage must be between 0 and 100.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', 'New') == 'New':
                vals['code'] = self.env['ir.sequence'].next_by_code('club.trainer') or 'New'
        return super().create(vals_list)

    @api.depends('class_ids', 'session_ids')
    def _compute_counts(self):
        for trainer in self:
            trainer.class_count = len(trainer.class_ids)
            trainer.session_count = len(trainer.session_ids)

    @api.depends('commission_ids.amount', 'commission_ids.state')
    def _compute_total_commission(self):
        for trainer in self:
            trainer.total_commission = sum(trainer.commission_ids.mapped('amount'))
            trainer.pending_commission = sum(
                trainer.commission_ids.filtered(
                    lambda c: c.state in ('draft', 'confirmed')
                ).mapped('amount')
            )

    def action_view_sessions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Sessions',
            'res_model': 'club.session',
            'view_mode': 'list,form',
            'views': [[False, 'list'], [False, 'form']],
            'domain': [('trainer_id', '=', self.id)],
            'context': {'default_trainer_id': self.id},
        }

    def action_view_commissions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Commissions',
            'res_model': 'club.trainer.commission',
            'view_mode': 'list,form',
            'views': [[False, 'list'], [False, 'form']],
            'domain': [('trainer_id', '=', self.id)],
            'context': {'default_trainer_id': self.id},
        }

    def action_create_commission_bill(self):
        """
        Create one Vendor Bill grouping ALL confirmed commissions
        for this trainer. The club pays the trainer via this bill.
        """
        self.ensure_one()
        confirmed = self.commission_ids.filtered(lambda c: c.state == 'confirmed')
        if not confirmed:
            raise UserError(
                'No confirmed commissions found.\n'
                'Please confirm the commission records first.'
            )

        product = self._get_or_create_commission_product()

        bill_lines = []
        for comm in confirmed:
            bill_lines.append((0, 0, {
                'product_id': product.id,
                'name': 'Commission: %s — %s' % (
                    comm.session_id.name if comm.session_id else str(comm.date),
                    self.name,
                ),
                'quantity': 1,
                'price_unit': comm.amount,
            }))

        bill = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.partner_id.id,
            'invoice_date': fields.Date.today(),
            'invoice_line_ids': bill_lines,
            'narration': 'Commission payment for trainer: %s' % self.name,
        })

        confirmed.write({'move_id': bill.id})

        return {
            'type': 'ir.actions.act_window',
            'name': 'Commission Bill — %s' % self.name,
            'res_model': 'account.move',
            'res_id': bill.id,
            'view_mode': 'form',
            'views': [[False, 'form']],
        }

    def _get_or_create_commission_product(self):
        # Search on product.template (type lives on template in Odoo 17+)
        tmpl = self.env['product.template'].search([
            ('name', '=', 'Trainer Commission'),
        ], limit=1)
        if not tmpl:
            tmpl = self.env['product.template'].create({
                'name': 'Trainer Commission',
                'type': 'service',
                'purchase_ok': True,
                'sale_ok': False,
            })
        return tmpl.product_variant_ids[:1]


class ClubTrainerCommission(models.Model):
    _name = 'club.trainer.commission'
    _description = 'Trainer Commission Record'
    _order = 'date desc'
    _rec_name = 'display_name'

    @api.depends('trainer_id', 'date')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = '%s — %s' % (rec.trainer_id.name or 'Commission', rec.date or '')

    trainer_id = fields.Many2one('club.trainer', string='Trainer', required=True, ondelete='cascade')
    session_id = fields.Many2one('club.session', string='Session', ondelete='set null')
    branch_id = fields.Many2one(related='trainer_id.branch_id', string='Branch', store=True)

    date = fields.Date(string='Date', required=True, default=fields.Date.context_today)
    attended_count = fields.Integer(string='Attended Sessions', default=1)
    session_revenue = fields.Float(string='Session Revenue', digits=(16, 2))
    commission_pct = fields.Float(string='Commission %', digits=(5, 2))
    amount = fields.Float(
        string='Commission Amount',
        compute='_compute_amount',
        store=True,
        digits=(16, 2),
    )

    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('paid', 'Paid'),
    ], string='Status', default='draft')

    # Vendor Bill that pays this commission
    move_id = fields.Many2one('account.move', string='Vendor Bill', copy=False)
    bill_payment_state = fields.Selection(
        related='move_id.payment_state',
        string='Bill Payment State',
        store=True,
    )

    notes = fields.Text(string='Notes')

    @api.depends('session_revenue', 'commission_pct')
    def _compute_amount(self):
        for rec in self:
            rec.amount = rec.session_revenue * rec.commission_pct / 100.0

    def action_confirm(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError('Only draft commissions can be confirmed.')
        self.write({'state': 'confirmed'})

    def action_create_bill(self):
        """Create a Vendor Bill for this single commission — club pays trainer."""
        self.ensure_one()
        if self.state != 'confirmed':
            raise UserError('Please confirm the commission before creating a bill.')

        # If bill already exists, open it
        if self.move_id:
            return {
                'type': 'ir.actions.act_window',
                'name': 'Vendor Bill',
                'res_model': 'account.move',
                'res_id': self.move_id.id,
                'view_mode': 'form',
                'views': [[False, 'form']],
            }

        product = self.trainer_id._get_or_create_commission_product()

        bill = self.env['account.move'].create({
            'move_type': 'in_invoice',                     # Vendor Bill
            'partner_id': self.trainer_id.partner_id.id,
            'invoice_date': fields.Date.today(),
            'invoice_line_ids': [(0, 0, {
                'product_id': product.id,
                'name': 'Commission: %s — %s' % (
                    self.session_id.name if self.session_id else str(self.date),
                    self.trainer_id.name,
                ),
                'quantity': 1,
                'price_unit': self.amount,
            })],
            'narration': 'Commission for trainer %s on %s' % (
                self.trainer_id.name, self.date
            ),
        })
        self.move_id = bill

        return {
            'type': 'ir.actions.act_window',
            'name': 'Vendor Bill',
            'res_model': 'account.move',
            'res_id': bill.id,
            'view_mode': 'form',
            'views': [[False, 'form']],
        }

    def action_mark_paid(self):
        """Manually mark paid — for cash payments done outside Odoo."""
        for rec in self:
            if rec.state != 'confirmed':
                raise UserError('Only confirmed commissions can be marked as paid.')
        self.write({'state': 'paid'})

    def action_reset_draft(self):
        for rec in self:
            if rec.move_id and rec.move_id.state == 'posted':
                raise UserError(
                    'Cannot reset: a posted vendor bill is already linked.\n'
                    'Cancel the bill first, then reset the commission.'
                )
        self.write({'state': 'draft', 'move_id': False})
