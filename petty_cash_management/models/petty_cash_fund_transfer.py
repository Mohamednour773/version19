# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PettyCashFundTransfer(models.Model):
    _name = 'petty.cash.fund.transfer'
    _description = 'Petty Cash Fund Transfer / Replenishment | تعبئة الصندوق'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'transfer_date desc, id desc'

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
    )
    fund_id = fields.Many2one(
        'petty.cash.fund',
        string='Petty Cash Fund',
        required=True,
        domain="[('state', '=', 'active')]",
        tracking=True,
    )
    custody_id = fields.Many2one(
        'hr.petty.cash',
        string='Related Custody (Replenishment)',
        tracking=True,
    )
    company_id = fields.Many2one(
        'res.company',
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        related='fund_id.currency_id',
        store=True,
        readonly=True,
    )
    source_journal_id = fields.Many2one(
        'account.journal',
        string='Source Journal (Main Cash / Bank)',
        required=True,
        domain="[('type', 'in', ['cash', 'bank']), ('company_id', '=', company_id)]",
        tracking=True,
    )
    amount = fields.Monetary(
        string='Transfer Amount',
        currency_field='currency_id',
        required=True,
        tracking=True,
    )
    transfer_date = fields.Date(
        string='Transfer Date',
        required=True,
        default=fields.Date.today,
        tracking=True,
    )
    reference = fields.Char(string='Reference / المرجع', tracking=True)
    state = fields.Selection(
        [
            ('draft', 'Draft / مسودة'),
            ('confirmed', 'Confirmed / مؤكد'),
            ('reviewed', 'Reviewed / مراجعة'),
            ('approved', 'Approved / معتمد'),
            ('posted', 'Posted / مرحّل'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
        copy=False,
    )
    is_reviewed = fields.Boolean(string='Reviewed', default=False, tracking=True)
    move_id = fields.Many2one(
        'account.move',
        string='Journal Entry',
        readonly=True,
        copy=False,
    )
    notes = fields.Text(string='Notes / ملاحظات')

    _sql_constraints = [
        ('amount_positive', 'CHECK(amount > 0)', 'Transfer amount must be positive.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('petty.cash.fund.transfer') or _('New')
        return super().create(vals_list)

    def action_confirm(self):
        self.ensure_one()
        self.write({'state': 'confirmed'})

    def action_review(self):
        self.ensure_one()
        self.write({'state': 'reviewed', 'is_reviewed': True})

    def action_approve(self):
        self.ensure_one()
        self.write({'state': 'approved'})

    def action_post(self):
        self.ensure_one()
        if self.state != 'approved':
            raise UserError(_('Only approved transfers can be posted.'))
        if not self.fund_id.account_id:
            raise UserError(_('Petty cash fund account is not configured.'))

        source_account = self.source_journal_id.default_account_id
        if not source_account:
            raise UserError(_('Source journal has no default account configured.'))

        move = self.env['account.move'].create({
            'journal_id': self.source_journal_id.id,
            'date': self.transfer_date,
            'ref': self.reference or self.name,
            'company_id': self.company_id.id,
            'line_ids': [
                (0, 0, {
                    'name': _('Fund Replenishment: %(fund)s', fund=self.fund_id.name),
                    'account_id': self.fund_id.account_id.id,
                    'debit': self.amount,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': _('Fund Replenishment: %(fund)s', fund=self.fund_id.name),
                    'account_id': source_account.id,
                    'debit': 0.0,
                    'credit': self.amount,
                }),
            ],
        })
        move.action_post()
        self.write({'state': 'posted', 'move_id': move.id})

    def action_reset_to_draft(self):
        self.ensure_one()
        if self.move_id and self.move_id.state == 'posted':
            raise UserError(_('Cannot reset a transfer with a posted journal entry.'))
        self.write({'state': 'draft'})

    @api.model
    def _cron_check_fund_balance(self):
        """Alert accountant when fund balance is below min_balance."""
        funds = self.env['petty.cash.fund'].search([('state', '=', 'active')])
        template = self.env.ref(
            'petty_cash_management.email_template_fund_low_balance', raise_if_not_found=False
        )
        for fund in funds:
            if fund.min_balance > 0 and fund.current_balance < fund.min_balance:
                if template:
                    template.send_mail(fund.id, force_send=True)
                fund.message_post(
                    body=_('⚠️ Fund balance (%(bal)s) is below minimum threshold (%(min)s).') % {
                        'bal': fund.currency_id.format(fund.current_balance),
                        'min': fund.currency_id.format(fund.min_balance),
                    },
                    subtype_xmlid='mail.mt_note',
                )
