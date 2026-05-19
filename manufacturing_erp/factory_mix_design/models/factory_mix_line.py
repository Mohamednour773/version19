# -*- coding: utf-8 -*-
from odoo import models, fields, api


class FactoryMixLine(models.Model):
    """
    Mix Line | بند الخلطة
    
    A single raw material entry within a mix design: product, quantity,
    UoM, cost, and expected waste percent.
    
    بند خامة واحد داخل تصميم الخلطة: المنتج، الكمية، وحدة القياس،
    التكلفة، ونسبة الهالك المتوقعة.
    """
    _name = 'factory.mix.line'
    _description = 'Mix Design Line | بند الخلطة'
    _order = 'sequence, id'

    mix_id = fields.Many2one('factory.mix', string='Mix | الخلطة', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    
    product_id = fields.Many2one(
        'product.product',
        string='Material | الخامة',
        required=True,
        domain="[('type', '!=', 'service')]",
    )
    quantity = fields.Float(
        string='Quantity | الكمية',
        required=True,
        digits='Product Unit of Measure',
        default=1.0,
    )
    uom_id = fields.Many2one(
        'uom.uom',
        string='UoM | الوحدة',
        required=True,
        default=lambda self: self.env.ref('uom.product_uom_kgm', raise_if_not_found=False),
    )
    waste_percent = fields.Float(
        string='Waste % | نسبة الهالك',
        digits=(5, 2),
        default=0.0,
        help='Expected waste/loss percentage | نسبة الهالك / الفقد المتوقعة',
    )
    quantity_with_waste = fields.Float(
        string='Qty with Waste | الكمية مع الهالك',
        compute='_compute_qty_with_waste',
        store=True,
        help='Quantity × (1 + waste%) | الكمية × (1 + نسبة الهالك)',
    )
    
    unit_cost = fields.Monetary(
        string='Unit Cost | تكلفة الوحدة',
        compute='_compute_unit_cost',
        store=True,
        readonly=False,
        currency_field='currency_id',
    )
    total_cost = fields.Monetary(
        string='Total Cost | إجمالي التكلفة',
        compute='_compute_total_cost',
        store=True,
        currency_field='currency_id',
    )
    
    notes = fields.Char(string='Notes | ملاحظات')
    currency_id = fields.Many2one(related='mix_id.currency_id', store=True)
    company_id = fields.Many2one(related='mix_id.company_id', store=True)

    @api.depends('quantity', 'waste_percent')
    def _compute_qty_with_waste(self):
        for rec in self:
            rec.quantity_with_waste = rec.quantity * (1 + (rec.waste_percent / 100.0))

    @api.depends('product_id')
    def _compute_unit_cost(self):
        for rec in self:
            if rec.product_id:
                rec.unit_cost = rec.product_id.standard_price
            else:
                rec.unit_cost = 0.0

    @api.depends('quantity_with_waste', 'unit_cost')
    def _compute_total_cost(self):
        for rec in self:
            rec.total_cost = rec.quantity_with_waste * rec.unit_cost

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.uom_id = self.product_id.uom_id
            self.unit_cost = self.product_id.standard_price
            if self.product_id.standard_waste_percent:
                self.waste_percent = self.product_id.standard_waste_percent
