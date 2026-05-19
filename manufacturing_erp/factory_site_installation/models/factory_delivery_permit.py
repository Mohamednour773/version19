# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class FactoryDeliveryPermit(models.Model):
    """
    Delivery Permit | إذن التوريد
    
    Document confirming receipt of products at the project site.
    Tracks delivered quantities and any items damaged during transit.
    
    وثيقة تؤكد استلام المنتجات في موقع المشروع.
    تتبع الكميات الموردة والقطع التالفة أثناء النقل.
    """
    _name = 'factory.delivery.permit'
    _description = 'Delivery Permit | إذن التوريد'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(string='Reference | المرجع', default='New', copy=False, readonly=True)
    date = fields.Datetime(string='Delivery Date | تاريخ التوريد', default=fields.Datetime.now, required=True)
    project_id = fields.Many2one('project.project', string='Project | المشروع', required=True, tracking=True)
    sector_id = fields.Many2one(
        'factory.sector', string='Sector | القطاع',
        domain="[('project_id','=',project_id)]")
    
    loading_permit_id = fields.Many2one(
        'factory.loading.permit', string='Loading Permit | إذن التحميل',
        domain="[('project_id','=',project_id),('state','=','loaded')]")
    
    site_receiver = fields.Char(string='Site Receiver | المستلم بالموقع')
    site_receiver_phone = fields.Char(string='Receiver Phone | تليفون المستلم')
    
    line_ids = fields.One2many('factory.delivery.permit.line', 'permit_id', string='Lines | البنود')
    
    total_delivered = fields.Float(string='Total Delivered | إجمالي الموَرَّد', compute='_compute_totals', store=True)
    total_damaged = fields.Float(string='Total Damaged | إجمالي التالف', compute='_compute_totals', store=True)
    
    state = fields.Selection([
        ('draft', 'Draft | مسودة'),
        ('confirmed', 'Confirmed | معتمد'),
        ('cancelled', 'Cancelled | ملغي'),
    ], string='Status | الحالة', default='draft', tracking=True)
    
    notes = fields.Text(string='Notes | ملاحظات')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('factory.delivery.permit') or 'New'
        return super().create(vals_list)

    @api.depends('line_ids.quantity_delivered', 'line_ids.quantity_damaged')
    def _compute_totals(self):
        for rec in self:
            rec.total_delivered = sum(rec.line_ids.mapped('quantity_delivered'))
            rec.total_damaged = sum(rec.line_ids.mapped('quantity_damaged'))

    def action_load_from_loading(self):
        for rec in self:
            if not rec.loading_permit_id:
                continue
            rec.line_ids.unlink()
            lines = []
            for ll in rec.loading_permit_id.line_ids:
                lines.append((0, 0, {
                    'product_id': ll.product_id.id,
                    'uom_id': ll.uom_id.id,
                    'quantity_loaded': ll.quantity,
                    'quantity_delivered': ll.quantity,
                    'quantity_damaged': 0.0,
                }))
            rec.line_ids = lines

    def action_confirm(self):
        for rec in self:
            if not rec.line_ids:
                raise ValidationError(_('Cannot confirm an empty delivery permit | لا يمكن تأكيد إذن توريد فارغ'))
            rec.state = 'confirmed'
            if rec.loading_permit_id:
                rec.loading_permit_id.delivery_permit_id = rec.id

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset(self):
        self.write({'state': 'draft'})


class FactoryDeliveryPermitLine(models.Model):
    _name = 'factory.delivery.permit.line'
    _description = 'Delivery Permit Line | بند إذن التوريد'

    permit_id = fields.Many2one('factory.delivery.permit', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product | المنتج', required=True)
    uom_id = fields.Many2one('uom.uom', string='UoM | الوحدة')
    
    quantity_loaded = fields.Float(string='Loaded | المحمَّل', digits='Product Unit of Measure')
    quantity_delivered = fields.Float(string='Delivered | الموَرَّد', digits='Product Unit of Measure')
    quantity_damaged = fields.Float(string='Damaged | التالف', digits='Product Unit of Measure')
    damage_notes = fields.Char(string='Damage Notes | ملاحظات التلف')

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.uom_id = self.product_id.uom_id
