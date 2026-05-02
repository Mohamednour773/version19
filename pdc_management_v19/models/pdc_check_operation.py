from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PDCCheckOperation(models.Model):
    """Immutable audit log of every state change and action on a PDC check."""

    _name = 'pdc.check.operation'
    _description = 'PDC Check Operation'
    _order = 'operation_date desc, id desc'

    name = fields.Char(string='Reference', required=True, copy=False,
                       default=lambda self: _('New'), readonly=True)
    check_id = fields.Many2one(
        'pdc.check', string='Check', required=True,
        ondelete='cascade', index=True, readonly=True,
    )
    operation_type = fields.Selection([
        ('register', 'Registration'),
        ('deposit', 'Deposit'),
        ('clear', 'Clearance'),
        ('bounce', 'Bounce'),
        ('settle', 'Settlement'),
        ('cancel', 'Cancellation'),
        ('print', 'Print'),
        ('deliver', 'Delivery'),
        ('pay', 'Payment'),
        ('return_guarantee', 'Guarantee Return'),
        ('activate_guarantee', 'Guarantee Activation'),
        ('update', 'Update'),
    ], string='Operation', required=True, readonly=True)
    operation_date = fields.Datetime(
        string='Date', default=fields.Datetime.now, readonly=True,
    )
    user_id = fields.Many2one(
        'res.users', string='By', default=lambda self: self.env.user,
        readonly=True,
    )
    from_state = fields.Char(string='From State', readonly=True)
    to_state = fields.Char(string='To State', readonly=True)
    amount = fields.Monetary(
        string='Amount', currency_field='currency_id', readonly=True,
    )
    currency_id = fields.Many2one(
        'res.currency', related='check_id.currency_id', readonly=True,
    )
    journal_id = fields.Many2one(
        'account.journal', string='Journal', readonly=True,
    )
    move_id = fields.Many2one(
        'account.move', string='Journal Entry', readonly=True,
    )
    notes = fields.Text(string='Notes', readonly=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company, readonly=True,
    )

    # ── display ──────────────────────────────────────────────────────────────
    @api.depends('name', 'operation_type')
    def _compute_display_name(self):
        for op in self:
            op.display_name = op.name or ''

    # ── CRUD overrides — immutable log ────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = (
                    self.env['ir.sequence'].next_by_code('pdc.check.operation') or _('New')
                )
        return super().create(vals_list)

    def write(self, vals):
        raise UserError(_(
            'Operations log is immutable. Record "%s" cannot be modified.',
            self.mapped('name'),
        ))

    def unlink(self):
        if not self.env.user.has_group('pdc_management_v19.group_pdc_accountant'):
            raise UserError(_(
                'Only PDC Accountants can delete operation records. '
                'These records are part of the audit trail.'
            ))
        return super().unlink()
