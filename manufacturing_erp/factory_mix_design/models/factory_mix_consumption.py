# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class FactoryMixConsumption(models.Model):
    """
    Mix Consumption Record | سجل استهلاك الخلطة
    
    Tracks actual material consumption per production batch.
    Used for theoretical vs actual comparison and waste analysis.
    
    تتبع الاستهلاك الفعلي للخامات لكل دفعة إنتاج.
    يُستخدم لمقارنة الاستهلاك النظري بالفعلي وتحليل الهالك.
    """
    _name = 'factory.mix.consumption'
    _description = 'Mix Consumption Record | سجل استهلاك الخلطة'
    _order = 'date desc, id desc'
    _inherit = ['mail.thread']

    name = fields.Char(string='Reference | المرجع', default='New', copy=False, readonly=True)
    date = fields.Date(string='Date | التاريخ', default=fields.Date.context_today, required=True)
    mix_id = fields.Many2one('factory.mix', string='Mix | الخلطة', required=True, ondelete='restrict')
    project_id = fields.Many2one('project.project', string='Project | المشروع')
    sector_id = fields.Many2one(
        'factory.sector',
        string='Sector | القطاع',
        domain="[('project_id','=',project_id)]",
    )
    production_ref = fields.Char(string='Production Order Ref | مرجع أمر الإنتاج')
    
    produced_quantity = fields.Float(
        string='Produced Quantity | الكمية المنتجة',
        required=True,
        digits='Product Unit of Measure',
    )
    
    consumption_line_ids = fields.One2many(
        'factory.mix.consumption.line', 'consumption_id',
        string='Material Lines | بنود الخامات',
    )
    
    # Cost summaries
    theoretical_cost = fields.Monetary(
        string='Theoretical Cost | التكلفة النظرية',
        compute='_compute_costs',
        store=True,
        currency_field='currency_id',
    )
    actual_cost = fields.Monetary(
        string='Actual Cost | التكلفة الفعلية',
        compute='_compute_costs',
        store=True,
        currency_field='currency_id',
    )
    variance_amount = fields.Monetary(
        string='Variance | الفرق',
        compute='_compute_costs',
        store=True,
        currency_field='currency_id',
    )
    variance_percent = fields.Float(
        string='Variance % | نسبة الفرق',
        compute='_compute_costs',
        store=True,
        digits=(5, 2),
    )
    
    state = fields.Selection([
        ('draft', 'Draft | مسودة'),
        ('confirmed', 'Confirmed | مؤكد'),
        ('cancelled', 'Cancelled | ملغي'),
    ], string='Status | الحالة', default='draft', tracking=True)
    
    currency_id = fields.Many2one(related='mix_id.currency_id', store=True)
    company_id = fields.Many2one(related='mix_id.company_id', store=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('factory.mix.consumption') or 'New'
        return super().create(vals_list)

    @api.depends('consumption_line_ids.theoretical_cost', 'consumption_line_ids.actual_cost')
    def _compute_costs(self):
        for rec in self:
            rec.theoretical_cost = sum(rec.consumption_line_ids.mapped('theoretical_cost'))
            rec.actual_cost = sum(rec.consumption_line_ids.mapped('actual_cost'))
            rec.variance_amount = rec.actual_cost - rec.theoretical_cost
            rec.variance_percent = (rec.variance_amount / rec.theoretical_cost * 100.0) if rec.theoretical_cost else 0.0

    def action_load_mix_lines(self):
        """Load theoretical lines from the mix design scaled to produced quantity."""
        for rec in self:
            rec.consumption_line_ids.unlink()
            if not rec.mix_id or rec.produced_quantity <= 0:
                continue
            scale = rec.produced_quantity / rec.mix_id.output_quantity if rec.mix_id.output_quantity else 0
            lines = []
            for ml in rec.mix_id.line_ids:
                theoretical_qty = ml.quantity * scale
                lines.append((0, 0, {
                    'product_id': ml.product_id.id,
                    'uom_id': ml.uom_id.id,
                    'theoretical_qty': theoretical_qty,
                    'actual_qty': theoretical_qty,  # default
                    'unit_cost': ml.unit_cost,
                }))
            rec.consumption_line_ids = lines

    def action_confirm(self):
        self.write({'state': 'confirmed'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})


class FactoryMixConsumptionLine(models.Model):
    _name = 'factory.mix.consumption.line'
    _description = 'Mix Consumption Line | بند استهلاك خلطة'

    consumption_id = fields.Many2one('factory.mix.consumption', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Material | الخامة', required=True)
    uom_id = fields.Many2one('uom.uom', string='UoM | الوحدة', required=True)
    
    theoretical_qty = fields.Float(string='Theoretical Qty | الكمية النظرية', digits='Product Unit of Measure')
    actual_qty = fields.Float(string='Actual Qty | الكمية الفعلية', digits='Product Unit of Measure')
    waste_qty = fields.Float(
        string='Waste Qty | كمية الهالك',
        compute='_compute_waste',
        store=True,
    )
    waste_percent = fields.Float(
        string='Waste % | نسبة الهالك',
        compute='_compute_waste',
        store=True,
        digits=(5, 2),
    )
    
    unit_cost = fields.Monetary(string='Unit Cost | تكلفة الوحدة', currency_field='currency_id')
    theoretical_cost = fields.Monetary(
        string='Theoretical Cost | التكلفة النظرية',
        compute='_compute_costs',
        store=True,
        currency_field='currency_id',
    )
    actual_cost = fields.Monetary(
        string='Actual Cost | التكلفة الفعلية',
        compute='_compute_costs',
        store=True,
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(related='consumption_id.currency_id', store=True)

    @api.depends('theoretical_qty', 'actual_qty')
    def _compute_waste(self):
        for rec in self:
            rec.waste_qty = max(0.0, rec.actual_qty - rec.theoretical_qty)
            rec.waste_percent = (rec.waste_qty / rec.theoretical_qty * 100.0) if rec.theoretical_qty else 0.0

    @api.depends('theoretical_qty', 'actual_qty', 'unit_cost')
    def _compute_costs(self):
        for rec in self:
            rec.theoretical_cost = rec.theoretical_qty * rec.unit_cost
            rec.actual_cost = rec.actual_qty * rec.unit_cost

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.uom_id = self.product_id.uom_id
            self.unit_cost = self.product_id.standard_price
