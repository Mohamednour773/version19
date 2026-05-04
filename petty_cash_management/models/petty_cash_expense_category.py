# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class PettyCashExpenseCategory(models.Model):
    _name = 'petty.cash.expense.category'
    _description = 'Petty Cash Expense Category'
    _order = 'sequence, name_en'

    name_en = fields.Char(string='Name (English)', required=True, translate=False)
    name_ar = fields.Char(string='الاسم (عربي)', required=True)
    name = fields.Char(string='Name', compute='_compute_name', store=True)
    sequence = fields.Integer(string='Sequence', default=10)
    account_id = fields.Many2one(
        'account.account',
        string='Default Expense Account',
        domain="[('account_type', 'like', 'expense')]",
    )
    requires_receipt = fields.Boolean(
        string='Requires Receipt',
        default=True,
        help='If checked, a receipt attachment is mandatory for settlement lines in this category.',
    )
    max_amount_per_line = fields.Float(
        string='Max Amount per Line',
        digits='Account',
        help='Leave 0 for no limit.',
    )
    active = fields.Boolean(string='Active', default=True)
    color = fields.Integer(string='Color Index')

    _sql_constraints = [
        ('name_en_uniq', 'unique(name_en)', 'English category name must be unique.'),
    ]

    @api.depends('name_en', 'name_ar')
    def _compute_name(self):
        for rec in self:
            rec.name = rec.name_ar or rec.name_en or ''

    def name_get(self):
        result = []
        for rec in self:
            name = f"{rec.name_ar} / {rec.name_en}" if rec.name_ar else rec.name_en
            result.append((rec.id, name))
        return result
