# -*- coding: utf-8 -*-
from odoo import models, fields, api


class FactoryEstimationLine(models.Model):
    """Estimation Line | بند المقايسة"""
    _name = 'factory.estimation.line'
    _description = 'Estimation Line | بند المقايسة'
    _order = 'sector_name, sequence, id'

    estimation_id = fields.Many2one('factory.estimation', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    
    sector_name = fields.Char(string='Sector | القطاع', help='Group lines into sectors | تجميع البنود في قطاعات')
    cost_category = fields.Selection([
        ('material', 'Materials | خامات'),
        ('mold', 'Molds | قوالب'),
        ('labor', 'Labor | عمالة'),
        ('installation', 'Installation | تركيب'),
        ('other', 'Other | أخرى'),
    ], string='Cost Category | فئة التكلفة', required=True, default='material')
    
    product_id = fields.Many2one('product.product', string='Product | المنتج')
    description = fields.Text(string='Description | الوصف')
    
    quantity = fields.Float(string='Quantity | الكمية', default=1.0, digits='Product Unit of Measure')
    uom_id = fields.Many2one('uom.uom', string='UoM | الوحدة')
    
    unit_cost = fields.Monetary(string='Unit Cost | تكلفة الوحدة', currency_field='currency_id')
    unit_price = fields.Monetary(string='Unit Price | سعر الوحدة', currency_field='currency_id')
    
    subtotal_cost = fields.Monetary(
        string='Subtotal Cost | إجمالي التكلفة',
        compute='_compute_subtotals', store=True, currency_field='currency_id')
    subtotal = fields.Monetary(
        string='Subtotal Price | إجمالي السعر',
        compute='_compute_subtotals', store=True, currency_field='currency_id')
    
    currency_id = fields.Many2one(related='estimation_id.currency_id', store=True)

    @api.depends('quantity', 'unit_cost', 'unit_price')
    def _compute_subtotals(self):
        for rec in self:
            rec.subtotal_cost = rec.quantity * rec.unit_cost
            rec.subtotal = rec.quantity * rec.unit_price

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.uom_id = self.product_id.uom_id
            self.unit_cost = self.product_id.standard_price
            self.unit_price = self.product_id.list_price
            self.description = self.product_id.name
