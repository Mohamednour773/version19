# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class FactoryInstallation(models.Model):
    """
    Site Installation Order | أمر التركيب بالموقع
    
    Tracks on-site installation work including:
    - Installation accessories consumption (tish, nails, brackets, angles, chemicals)
    - Finishing materials consumption (sefito, epoxy, putty, paint)
    - Labor on site
    - Daily site expenses
    
    يتتبع أعمال التركيب بالموقع شاملةً:
    - استهلاك إكسسوارات التركيب (تيش، مسامير، براكيت، زوايا، كيماويات)
    - استهلاك خامات التشطيب (سفيتو، إيبوكسي، معجون، دهانات)
    - العمالة بالموقع
    - المصروفات اليومية للموقع
    """
    _name = 'factory.installation'
    _description = 'Site Installation Order | أمر التركيب بالموقع'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(string='Reference | المرجع', default='New', copy=False, readonly=True)
    date = fields.Date(string='Date | التاريخ', default=fields.Date.context_today, required=True)
    project_id = fields.Many2one('project.project', string='Project | المشروع', required=True, tracking=True)
    sector_id = fields.Many2one(
        'factory.sector', string='Sector | القطاع',
        domain="[('project_id','=',project_id)]", required=True, tracking=True)
    
    date_start = fields.Date(string='Start Date | تاريخ البدء')
    date_end = fields.Date(string='End Date | تاريخ الانتهاء')
    
    # Quantities | الكميات
    quantity_to_install = fields.Float(
        string='Quantity to Install | الكمية المطلوب تركيبها',
        digits='Product Unit of Measure')
    quantity_installed = fields.Float(
        string='Installed Quantity | الكمية المركبة',
        digits='Product Unit of Measure', tracking=True)
    uom_id = fields.Many2one('uom.uom', string='UoM | الوحدة', related='sector_id.uom_id', store=True)
    
    # Material consumption | استهلاك الخامات
    accessory_line_ids = fields.One2many(
        'factory.installation.accessory', 'installation_id',
        string='Installation Accessories | إكسسوارات التركيب')
    finishing_line_ids = fields.One2many(
        'factory.installation.finishing', 'installation_id',
        string='Finishing Materials | خامات التشطيب')
    
    # Labor | العمالة
    labor_hours = fields.Float(string='Labor Hours | ساعات العمالة')
    labor_rate = fields.Monetary(string='Labor Rate | السعر/الساعة', currency_field='currency_id')
    labor_cost = fields.Monetary(
        string='Labor Cost | تكلفة العمالة',
        compute='_compute_costs', store=True, currency_field='currency_id')
    
    # Cost rollup | تجميع التكلفة
    accessory_cost = fields.Monetary(
        string='Accessories Cost | تكلفة الإكسسوارات',
        compute='_compute_costs', store=True, currency_field='currency_id')
    finishing_cost = fields.Monetary(
        string='Finishing Cost | تكلفة التشطيب',
        compute='_compute_costs', store=True, currency_field='currency_id')
    expenses_cost = fields.Monetary(
        string='Site Expenses | مصاريف الموقع',
        compute='_compute_costs', store=True, currency_field='currency_id')
    total_cost = fields.Monetary(
        string='Total Cost | إجمالي التكلفة',
        compute='_compute_costs', store=True, currency_field='currency_id')
    cost_per_unit = fields.Monetary(
        string='Cost per Unit | تكلفة الوحدة',
        compute='_compute_costs', store=True, currency_field='currency_id')
    
    expense_ids = fields.One2many('factory.site.expense', 'installation_id', string='Site Expenses | مصاريف الموقع')
    
    state = fields.Selection([
        ('draft', 'Draft | مسودة'),
        ('in_progress', 'In Progress | قيد التنفيذ'),
        ('done', 'Done | منتهي'),
        ('cancelled', 'Cancelled | ملغي'),
    ], string='Status | الحالة', default='draft', tracking=True)
    
    notes = fields.Text(string='Notes | ملاحظات')
    analytic_account_id = fields.Many2one('account.analytic.account', string='Analytic Account | الحساب التحليلي')
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    user_id = fields.Many2one('res.users', string='Site Supervisor | مشرف الموقع', default=lambda self: self.env.user)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('factory.installation') or 'New'
        return super().create(vals_list)

    @api.depends('accessory_line_ids.total_cost', 'finishing_line_ids.total_cost',
                 'expense_ids.amount', 'labor_hours', 'labor_rate', 'quantity_installed')
    def _compute_costs(self):
        for rec in self:
            rec.accessory_cost = sum(rec.accessory_line_ids.mapped('total_cost'))
            rec.finishing_cost = sum(rec.finishing_line_ids.mapped('total_cost'))
            rec.expenses_cost = sum(rec.expense_ids.mapped('amount'))
            rec.labor_cost = rec.labor_hours * rec.labor_rate
            rec.total_cost = rec.accessory_cost + rec.finishing_cost + rec.expenses_cost + rec.labor_cost
            rec.cost_per_unit = (rec.total_cost / rec.quantity_installed) if rec.quantity_installed else 0.0

    @api.onchange('sector_id')
    def _onchange_sector_id(self):
        if self.sector_id:
            self.quantity_to_install = self.sector_id.delivered_quantity - self.sector_id.installed_quantity
            if self.sector_id.analytic_account_id:
                self.analytic_account_id = self.sector_id.analytic_account_id

    def action_start(self):
        for rec in self:
            rec.state = 'in_progress'
            if not rec.date_start:
                rec.date_start = fields.Date.context_today(rec)

    def action_done(self):
        for rec in self:
            if rec.quantity_installed <= 0:
                raise ValidationError(_('Please record installed quantity before marking done | يرجى تسجيل الكمية المركبة قبل الإنهاء'))
            rec.state = 'done'
            if not rec.date_end:
                rec.date_end = fields.Date.context_today(rec)

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset(self):
        self.write({'state': 'draft'})


class FactoryInstallationAccessory(models.Model):
    """
    Installation Accessory Line | بند إكسسوار التركيب
    
    Examples: tish, nails, brackets, angles, fixing chemicals.
    أمثلة: تيش، مسامير، براكيت، زوايا، كيماويات تثبيت.
    """
    _name = 'factory.installation.accessory'
    _description = 'Installation Accessory | إكسسوار تركيب'

    installation_id = fields.Many2one('factory.installation', required=True, ondelete='cascade')
    product_id = fields.Many2one(
        'product.product', string='Accessory | الإكسسوار', required=True)
    quantity = fields.Float(string='Qty | الكمية', digits='Product Unit of Measure', required=True)
    uom_id = fields.Many2one('uom.uom', string='UoM | الوحدة')
    unit_cost = fields.Monetary(string='Unit Cost | تكلفة الوحدة', currency_field='currency_id')
    total_cost = fields.Monetary(
        string='Total Cost | إجمالي التكلفة',
        compute='_compute_total', store=True, currency_field='currency_id')
    notes = fields.Char(string='Notes | ملاحظات')
    currency_id = fields.Many2one(related='installation_id.currency_id', store=True)

    @api.depends('quantity', 'unit_cost')
    def _compute_total(self):
        for rec in self:
            rec.total_cost = rec.quantity * rec.unit_cost

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.uom_id = self.product_id.uom_id
            self.unit_cost = self.product_id.standard_price


class FactoryInstallationFinishing(models.Model):
    """
    Finishing Material Line | بند خامة تشطيب
    
    Examples: sefito, epoxy, putty, paint.
    أمثلة: سفيتو، إيبوكسي، معجون، دهانات.
    """
    _name = 'factory.installation.finishing'
    _description = 'Finishing Material | خامة تشطيب'

    installation_id = fields.Many2one('factory.installation', required=True, ondelete='cascade')
    product_id = fields.Many2one(
        'product.product', string='Material | الخامة', required=True)
    quantity = fields.Float(string='Qty | الكمية', digits='Product Unit of Measure', required=True)
    uom_id = fields.Many2one('uom.uom', string='UoM | الوحدة')
    unit_cost = fields.Monetary(string='Unit Cost | تكلفة الوحدة', currency_field='currency_id')
    total_cost = fields.Monetary(
        string='Total Cost | إجمالي التكلفة',
        compute='_compute_total', store=True, currency_field='currency_id')
    notes = fields.Char(string='Notes | ملاحظات')
    currency_id = fields.Many2one(related='installation_id.currency_id', store=True)

    @api.depends('quantity', 'unit_cost')
    def _compute_total(self):
        for rec in self:
            rec.total_cost = rec.quantity * rec.unit_cost

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.uom_id = self.product_id.uom_id
            self.unit_cost = self.product_id.standard_price
