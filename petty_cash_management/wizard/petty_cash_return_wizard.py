# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PettyCashReturnWizard(models.TransientModel):
    _name = 'petty.cash.return.wizard'
    _description = 'Return Petty Cash Amount Wizard'

    custody_id = fields.Many2one('hr.petty.cash', string='Custody', required=True)
    return_amount = fields.Monetary(
        string='Amount to Return / المبلغ المردود',
        currency_field='currency_id',
        required=True,
    )
    currency_id = fields.Many2one(
        related='custody_id.currency_id',
        readonly=True,
    )
    paid_amount = fields.Monetary(
        related='custody_id.paid_amount',
        string='Amount Paid',
        currency_field='currency_id',
        readonly=True,
    )
    return_date = fields.Date(string='Return Date', default=fields.Date.today, required=True)
    notes = fields.Text(string='Notes / ملاحظات')

    @api.onchange('custody_id')
    def _onchange_custody(self):
        if self.custody_id:
            self.return_amount = self.custody_id.paid_amount

    @api.constrains('return_amount', 'paid_amount')
    def _check_return_amount(self):
        for rec in self:
            if rec.return_amount <= 0:
                raise UserError(_('Return amount must be greater than zero.'))
            if rec.return_amount > rec.paid_amount:
                raise UserError(_('Return amount cannot exceed the paid amount.'))

    def action_confirm_return(self):
        self.ensure_one()
        config = self.env['petty.cash.config.settings']._get_values()
        custody_account = config.get('custody_account_id')  # fixed: was 'default_custody_account_id'
        if not custody_account:
            raise UserError(_('Employee Custody Account is not configured in Petty Cash Settings.'))

        fund = self.custody_id.petty_fund_id
        move = self.env['account.move'].create({
            'journal_id': fund.journal_id.id,
            'date': self.return_date,
            'ref': _('Return: %(name)s', name=self.custody_id.name),
            'company_id': self.custody_id.company_id.id,
            'line_ids': [
                (0, 0, {
                    'name': _('Cash Return from %(emp)s', emp=self.custody_id.employee_id.name),
                    'account_id': fund.account_id.id,
                    'debit': self.return_amount,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': _('Cash Return from %(emp)s', emp=self.custody_id.employee_id.name),
                    'account_id': custody_account,
                    'debit': 0.0,
                    'credit': self.return_amount,
                    'partner_id': (
                        self.custody_id.employee_id.work_contact_id.id
                        if self.custody_id.employee_id.work_contact_id else False
                    ),
                }),
            ],
        })
        move.action_post()
        self.custody_id.write({
            'state': 'returned',
            'actual_return_date': self.return_date,
        })
        self.custody_id.message_post(
            body=_('✅ Amount %s returned on %s. Journal Entry: %s') % (
                self.custody_id.currency_id.format(self.return_amount),
                self.return_date,
                move.name,
            ),
        )
        return {'type': 'ir.actions.act_window_close'}
