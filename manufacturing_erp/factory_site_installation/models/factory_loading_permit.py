# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class FactoryLoadingPermit(models.Model):
    """
    Loading Permit | إذن تحميل
    
    Document issued when products are loaded from the factory onto a vehicle
    for shipment to the project site.
    
    وثيقة تُصدر عند تحميل المنتجات من المصنع على السيارة لشحنها لموقع المشروع.
    """
    _name = 'factory.loading.permit'
    _description = 'Loading Permit | إذن التحميل'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(string='Reference | المرجع', default='New', copy=False, readonly=True)
    date = fields.Datetime(string='Loading Date | تاريخ التحميل', default=fields.Datetime.now, required=True)
    project_id = fields.Many2one('project.project', string='Project | المشروع', required=True, tracking=True)
    sector_id = fields.Many2one(
        'factory.sector', string='Sector | القطاع',
        domain="[('project_id','=',project_id)]")
    
    # Truck info | بيانات الشاحنة
    vehicle_number = fields.Char(string='Vehicle Number | رقم السيارة', tracking=True)
    driver_name = fields.Char(string='Driver Name | اسم السائق')
    driver_phone = fields.Char(string='Driver Phone | تليفون السائق')
    destination = fields.Char(string='Destination | الوجهة')
    
    line_ids = fields.One2many('factory.loading.permit.line', 'permit_id', string='Lines | البنود')
    
    total_quantity = fields.Float(
        string='Total Quantity | إجمالي الكمية',
        compute='_compute_totals', store=True)
    
    state = fields.Selection([
        ('draft', 'Draft | مسودة'),
        ('confirmed', 'Confirmed | معتمد'),
        ('loaded', 'Loaded | تم التحميل'),
        ('cancelled', 'Cancelled | ملغي'),
    ], string='Status | الحالة', default='draft', tracking=True)
    
    delivery_permit_id = fields.Many2one('factory.delivery.permit', string='Delivery Permit | إذن التوريد', readonly=True)
    notes = fields.Text(string='Notes | ملاحظات')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('factory.loading.permit') or 'New'
        return super().create(vals_list)

    @api.depends('line_ids.quantity')
    def _compute_totals(self):
        for rec in self:
            rec.total_quantity = sum(rec.line_ids.mapped('quantity'))

    def action_confirm(self):
        for rec in self:
            if not rec.line_ids:
                raise ValidationError(_('Cannot confirm an empty loading permit | لا يمكن تأكيد إذن تحميل فارغ'))
            rec.state = 'confirmed'

    def action_load(self):
        self.write({'state': 'loaded'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset(self):
        self.write({'state': 'draft'})


class FactoryLoadingPermitLine(models.Model):
    _name = 'factory.loading.permit.line'
    _description = 'Loading Permit Line | بند إذن التحميل'

    permit_id = fields.Many2one('factory.loading.permit', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product | المنتج', required=True)
    quantity = fields.Float(string='Quantity | الكمية', digits='Product Unit of Measure', required=True)
    uom_id = fields.Many2one('uom.uom', string='UoM | الوحدة', related='product_id.uom_id', readonly=False)
    notes = fields.Char(string='Notes | ملاحظات')

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.uom_id = self.product_id.uom_id
