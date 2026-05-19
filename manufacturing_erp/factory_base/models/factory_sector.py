# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class FactorySector(models.Model):
    """
    Project Sector | قطاع المشروع
    
    Each project may contain multiple sectors. A sector represents a 
    sub-division of work with potentially different mix designs, molds,
    and finishing requirements.
    
    كل مشروع ممكن يحتوي على قطاعات متعددة. القطاع هو تقسيم فرعي للعمل
    قد يكون له خلطات وقوالب وتشطيبات مختلفة.
    """
    _name = 'factory.sector'
    _description = 'Project Sector | قطاع المشروع'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, project_id, name'

    name = fields.Char(
        string='Sector Name | اسم القطاع',
        required=True,
        tracking=True,
    )
    code = fields.Char(
        string='Sector Code | كود القطاع',
        required=True,
        tracking=True,
    )
    sequence = fields.Integer(string='Sequence | الترتيب', default=10)
    project_id = fields.Many2one(
        'project.project',
        string='Project | المشروع',
        required=True,
        ondelete='cascade',
        tracking=True,
    )
    partner_id = fields.Many2one(
        related='project_id.partner_id',
        string='Customer | العميل',
        store=True,
        readonly=True,
    )
    description = fields.Text(string='Description | الوصف')
    
    # Quantities | الكميات
    planned_quantity = fields.Float(
        string='Planned Quantity | الكمية المخططة',
        digits='Product Unit of Measure',
        tracking=True,
    )
    uom_id = fields.Many2one(
        'uom.uom',
        string='Unit of Measure | وحدة القياس',
        required=True,
        default=lambda self: self.env.ref('uom.product_uom_meter', raise_if_not_found=False),
    )
    produced_quantity = fields.Float(
        string='Produced Quantity | الكمية المنتجة',
        compute='_compute_quantities',
        store=True,
    )
    delivered_quantity = fields.Float(
        string='Delivered Quantity | الكمية الموردة',
        compute='_compute_quantities',
        store=True,
    )
    installed_quantity = fields.Float(
        string='Installed Quantity | الكمية المركبة',
        compute='_compute_quantities',
        store=True,
    )
    remaining_to_produce = fields.Float(
        string='Remaining to Produce | المتبقي للتصنيع',
        compute='_compute_remaining',
        store=True,
    )
    remaining_to_deliver = fields.Float(
        string='Remaining to Deliver | المتبقي للتوريد',
        compute='_compute_remaining',
        store=True,
    )
    
    # Pricing | التسعير
    unit_price = fields.Monetary(
        string='Unit Price | سعر الوحدة',
        currency_field='currency_id',
        tracking=True,
    )
    total_value = fields.Monetary(
        string='Total Value | القيمة الإجمالية',
        compute='_compute_total_value',
        store=True,
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        related='project_id.company_id.currency_id',
        store=True,
        readonly=True,
    )
    
    # Linked Records | السجلات المرتبطة
    product_id = fields.Many2one(
        'product.product',
        string='Product | المنتج',
        domain=[('type', '=', 'consu')],
        help='The manufactured product for this sector | المنتج المصنع لهذا القطاع',
    )
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account | الحساب التحليلي',
        help='Cost center for tracking expenses | مركز التكلفة لتتبع المصروفات',
    )
    
    # Status | الحالة
    state = fields.Selection([
        ('draft', 'Draft | مسودة'),
        ('confirmed', 'Confirmed | مؤكد'),
        ('in_production', 'In Production | تحت الإنتاج'),
        ('delivering', 'Delivering | جاري التوريد'),
        ('installing', 'Installing | جاري التركيب'),
        ('done', 'Done | منتهي'),
        ('cancelled', 'Cancelled | ملغي'),
    ], string='Status | الحالة', default='draft', tracking=True)
    
    company_id = fields.Many2one(
        related='project_id.company_id',
        store=True,
        readonly=True,
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('code_project_uniq', 'unique(code, project_id)',
         'Sector code must be unique per project! | كود القطاع يجب أن يكون فريداً لكل مشروع!'),
    ]

    @api.depends('planned_quantity', 'unit_price')
    def _compute_total_value(self):
        for rec in self:
            rec.total_value = rec.planned_quantity * rec.unit_price

    @api.depends('planned_quantity', 'produced_quantity', 'delivered_quantity')
    def _compute_remaining(self):
        for rec in self:
            rec.remaining_to_produce = max(0.0, rec.planned_quantity - rec.produced_quantity)
            rec.remaining_to_deliver = max(0.0, rec.produced_quantity - rec.delivered_quantity)

    def _compute_quantities(self):
        """
        To be overridden in factory_production / factory_site_installation
        to compute actual produced/delivered/installed amounts.
        يتم استبدالها في الموديولات الفرعية لحساب الكميات الفعلية.
        """
        for rec in self:
            rec.produced_quantity = 0.0
            rec.delivered_quantity = 0.0
            rec.installed_quantity = 0.0

    def action_confirm(self):
        for rec in self:
            rec.state = 'confirmed'
            if not rec.analytic_account_id and rec.project_id.analytic_account_id:
                rec.analytic_account_id = rec.project_id.analytic_account_id

    def action_start_production(self):
        self.write({'state': 'in_production'})

    def action_done(self):
        self.write({'state': 'done'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset_to_draft(self):
        self.write({'state': 'draft'})
