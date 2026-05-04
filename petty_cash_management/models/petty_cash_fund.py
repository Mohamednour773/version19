# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PettyCashFund(models.Model):
    _name = 'petty.cash.fund'
    _description = 'Petty Cash Fund'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char(string='Fund Name', required=True, tracking=True)
    name_ar = fields.Char(string='اسم الصندوق', required=True, tracking=True)
    code = fields.Char(string='Fund Code', required=True, copy=False)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
        store=True,
        readonly=True,
    )
    custodian_id = fields.Many2one(
        'hr.employee',
        string='Custodian / أمين الصندوق',
        required=True,
        tracking=True,
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Petty Cash Journal',
        required=True,
        domain="[('type', 'in', ['cash', 'bank']), ('company_id', '=', company_id)]",
        tracking=True,
    )
    account_id = fields.Many2one(
        'account.account',
        string='Petty Cash Account',
        required=True,
        domain="[('company_ids', 'in', [company_id])]",
        tracking=True,
    )
    current_balance = fields.Monetary(
        string='Current Balance / الرصيد الحالي',
        compute='_compute_current_balance',
        store=True,
        currency_field='currency_id',
    )
    max_balance = fields.Monetary(
        string='Maximum Balance',
        currency_field='currency_id',
        tracking=True,
    )
    min_balance = fields.Monetary(
        string='Minimum Balance (Replenishment Threshold)',
        currency_field='currency_id',
        tracking=True,
    )
    state = fields.Selection(
        [('active', 'Active / نشط'), ('suspended', 'Suspended / موقوف'), ('closed', 'Closed / مغلق')],
        string='Status',
        default='active',
        required=True,
        tracking=True,
    )
    branch_name = fields.Char(string='Branch / الفرع', help='Branch or cost center name.')
    custody_ids = fields.One2many('hr.petty.cash', 'petty_fund_id', string='Custodies')
    transfer_ids = fields.One2many('petty.cash.fund.transfer', 'fund_id', string='Fund Transfers')
    payment_ids = fields.One2many('account.payment', 'petty_fund_id', string='Direct Payments')

    custody_count = fields.Integer(compute='_compute_counts')
    transfer_count = fields.Integer(compute='_compute_counts')
    payment_count = fields.Integer(compute='_compute_counts')

    notes = fields.Text(string='Notes / ملاحظات')

    _sql_constraints = [
        ('code_company_uniq', 'unique(code, company_id)', 'Fund code must be unique per company.'),
    ]

    @api.depends('journal_id', 'account_id')
    def _compute_current_balance(self):
        """Compute balance from posted journal entry lines on the petty cash account."""
        for fund in self:
            if not fund.account_id or not fund.company_id:
                fund.current_balance = 0.0
                continue
            domain = [
                ('account_id', '=', fund.account_id.id),
                ('move_id.state', '=', 'posted'),
                ('company_id', '=', fund.company_id.id),
            ]
            lines = self.env['account.move.line'].search(domain)
            balance = sum(lines.mapped('debit')) - sum(lines.mapped('credit'))
            fund.current_balance = balance

    def _compute_counts(self):
        for fund in self:
            fund.custody_count = len(fund.custody_ids)
            fund.transfer_count = len(fund.transfer_ids)
            fund.payment_count = len(fund.payment_ids)

    def action_suspend(self):
        self.ensure_one()
        self.state = 'suspended'

    def action_reactivate(self):
        self.ensure_one()
        self.state = 'active'

    def action_close(self):
        self.ensure_one()
        active_custodies = self.custody_ids.filtered(
            lambda c: c.state not in ('closed', 'refused', 'returned')
        )
        if active_custodies:
            raise UserError(_('Cannot close fund with active custodies. Please settle all custodies first.'))
        self.state = 'closed'

    def action_view_custodies(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Custodies'),
            'res_model': 'hr.petty.cash',
            'view_mode': 'list,form',
            'domain': [('petty_fund_id', '=', self.id)],
            'context': {'default_petty_fund_id': self.id},
        }

    def action_view_transfers(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Fund Transfers'),
            'res_model': 'petty.cash.fund.transfer',
            'view_mode': 'list,form',
            'domain': [('fund_id', '=', self.id)],
            'context': {'default_fund_id': self.id},
        }

    def action_view_payments(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Direct Payments'),
            'res_model': 'account.payment',
            'view_mode': 'list,form',
            'domain': [('petty_fund_id', '=', self.id)],
            'context': {'default_petty_fund_id': self.id},
        }

    def _check_balance_warning(self, amount):
        """Returns True if payment would exceed balance, raises or warns based on config."""
        config = self.env['ir.config_parameter'].sudo()
        allow_exceed = config.get_param('petty_cash.allow_exceed_fund_balance', 'True') == 'True'
        if self.current_balance < amount:
            if not allow_exceed:
                raise UserError(_(
                    'Insufficient petty cash fund balance.\nAvailable: %(balance)s | Requested: %(amount)s',
                    balance=self.currency_id.format(self.current_balance),
                    amount=self.currency_id.format(amount),
                ))
            return True  # warning only
        return False
