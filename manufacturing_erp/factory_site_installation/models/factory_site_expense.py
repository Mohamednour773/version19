# -*- coding: utf-8 -*-
from odoo import models, fields, api


class FactorySiteExpense(models.Model):
    """
    Site Daily Expense | مصروف يومي للموقع
    
    Daily expenses incurred at the site during installation: food, transport,
    misc supplies, equipment rental, etc.
    
    مصروفات يومية تحدث في الموقع أثناء التركيب: أكل، مواصلات، مستلزمات،
    إيجار معدات، إلخ.
    """
    _name = 'factory.site.expense'
    _description = 'Site Daily Expense | مصروف موقع يومي'
    _order = 'date desc, id desc'

    name = fields.Char(string='Description | الوصف', required=True)
    date = fields.Date(string='Date | التاريخ', default=fields.Date.context_today, required=True)
    installation_id = fields.Many2one('factory.installation', string='Installation | التركيب', ondelete='cascade')
    project_id = fields.Many2one('project.project', related='installation_id.project_id', store=True, readonly=True)
    sector_id = fields.Many2one('factory.sector', related='installation_id.sector_id', store=True, readonly=True)
    
    expense_category = fields.Selection([
        ('food', 'Food | أكل'),
        ('transport', 'Transport | مواصلات'),
        ('supplies', 'Supplies | مستلزمات'),
        ('equipment_rental', 'Equipment Rental | إيجار معدات'),
        ('accommodation', 'Accommodation | إقامة'),
        ('other', 'Other | أخرى'),
    ], string='Category | الفئة', default='other', required=True)
    
    amount = fields.Monetary(string='Amount | المبلغ', currency_field='currency_id', required=True)
    paid_by = fields.Many2one('hr.employee', string='Paid By | المدفوع بواسطة')
    receipt_number = fields.Char(string='Receipt # | رقم الإيصال')
    notes = fields.Text(string='Notes | ملاحظات')
    
    currency_id = fields.Many2one(related='installation_id.currency_id', store=True)
    company_id = fields.Many2one(related='installation_id.company_id', store=True)
