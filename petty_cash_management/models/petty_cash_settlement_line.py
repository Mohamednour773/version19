# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class PettyCashSettlementLine(models.Model):
    _name = 'petty.cash.settlement.line'
    _inherit = ['analytic.mixin']
    _description = 'Petty Cash Settlement Line'
    _order = 'expense_date, id'

    settlement_id = fields.Many2one(
        'petty.cash.settlement',
        string='Settlement',
        required=True,
        ondelete='cascade',
    )
    company_id = fields.Many2one(
        related='settlement_id.company_id',
        store=True,
    )
    currency_id = fields.Many2one(
        related='settlement_id.currency_id',
        store=True,
    )

    # ── Description ───────────────────────────────────────────────────────────
    description_en = fields.Char(string='Description (EN)')
    description_ar = fields.Char(string='البيان (عربي)')
    description = fields.Char(
        string='Description',
        compute='_compute_description',
        store=True,
    )

    # ── Category & Account ────────────────────────────────────────────────────
    category_id = fields.Many2one(
        'petty.cash.expense.category',
        string='Category / الفئة',
        required=True,
    )
    expense_account_id = fields.Many2one(
        'account.account',
        string='Expense Account',
        required=True,
        domain="[('account_type', 'like', 'expense'), ('company_ids', 'in', [company_id])]",
    )


    # ── Amount & Tax ──────────────────────────────────────────────────────────
    amount = fields.Monetary(
        string='Amount / المبلغ',
        currency_field='currency_id',
        required=True,
    )
    tax_ids = fields.Many2many(
        'account.tax',
        string='Taxes',
        domain="[('type_tax_use', '=', 'purchase'), ('company_id', '=', company_id)]",
    )
    tax_amount = fields.Monetary(
        string='Tax Amount',
        compute='_compute_tax_amount',
        store=True,
        currency_field='currency_id',
    )
    total_amount = fields.Monetary(
        string='Total (with Tax)',
        compute='_compute_tax_amount',
        store=True,
        currency_field='currency_id',
    )

    # ── Date & Receipt ────────────────────────────────────────────────────────
    expense_date = fields.Date(string='Expense Date', required=True, default=fields.Date.today)
    receipt_attachment_ids = fields.Many2many(
        'ir.attachment',
        'petty_cash_settlement_line_attachment_rel',
        'line_id',
        'attachment_id',
        string='Receipts / الإيصالات',
        help='Attach receipt scans or PDFs. Stored as proper attachments, not inline binary.',
    )
    bill_id = fields.Many2one(
        'account.move',
        string='Related Bill',
        domain="[('move_type', '=', 'in_invoice'), ('state', '=', 'posted')]",
    )

    # ── Computed ──────────────────────────────────────────────────────────────
    @api.depends('description_en', 'description_ar')
    def _compute_description(self):
        for rec in self:
            rec.description = rec.description_ar or rec.description_en or ''

    @api.depends('amount', 'tax_ids')
    def _compute_tax_amount(self):
        for rec in self:
            if rec.tax_ids:
                taxes = rec.tax_ids.compute_all(rec.amount, rec.currency_id, 1.0)
                rec.tax_amount = taxes['total_included'] - taxes['total_excluded']
                rec.total_amount = taxes['total_included']
            else:
                rec.tax_amount = 0.0
                rec.total_amount = rec.amount

    @api.onchange('category_id')
    def _onchange_category_id(self):
        if self.category_id and self.category_id.account_id:
            self.expense_account_id = self.category_id.account_id

    @api.constrains('amount', 'category_id')
    def _check_max_amount(self):
        for rec in self:
            if rec.category_id and rec.category_id.max_amount_per_line > 0:
                if rec.amount > rec.category_id.max_amount_per_line:
                    raise ValidationError(_(
                        'Amount %(amount)s exceeds the maximum allowed per line (%(max)s) for category "%(cat)s".',
                        amount=rec.amount,
                        max=rec.category_id.max_amount_per_line,
                        cat=rec.category_id.name_ar or rec.category_id.name_en,
                    ))

    @api.constrains('receipt_attachment_ids', 'category_id', 'settlement_id')
    def _check_receipt_required(self):
        for rec in self:
            if (rec.category_id and rec.category_id.requires_receipt
                    and not rec.receipt_attachment_ids
                    and rec.settlement_id.state not in ('draft', 'submitted')):
                raise ValidationError(_(
                    'A receipt is required for category "%s".',
                    rec.category_id.name_ar or rec.category_id.name_en,
                ))
