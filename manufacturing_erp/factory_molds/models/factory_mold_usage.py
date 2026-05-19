# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class FactoryMoldUsage(models.Model):
    """
    Mold Usage Record | سجل استخدام القالب
    
    Each time a mold is used (in production), a usage record is created.
    This is the basis for accurate cost allocation per produced unit.
    
    كل مرة يتم فيها استخدام القالب في الإنتاج يتم إنشاء سجل استخدام.
    وهذا أساس التوزيع الدقيق للتكلفة على كل وحدة منتجة.
    """
    _name = 'factory.mold.usage'
    _description = 'Mold Usage Record | سجل استخدام القالب'
    _order = 'usage_date desc, id desc'
    _inherit = ['mail.thread']

    name = fields.Char(string='Reference | المرجع', default='New', copy=False, readonly=True)
    mold_id = fields.Many2one(
        'factory.mold',
        string='Mold | القالب',
        required=True,
        ondelete='restrict',
        tracking=True,
    )
    usage_date = fields.Date(
        string='Usage Date | تاريخ الاستخدام',
        default=fields.Date.context_today,
        required=True,
        tracking=True,
    )
    use_count = fields.Integer(
        string='Use Count | عدد الاستخدامات',
        default=1,
        required=True,
        help='Number of uses logged in this record | عدد مرات الاستخدام في هذا السجل',
    )
    produced_quantity = fields.Float(
        string='Produced Quantity | الكمية المنتجة',
        digits='Product Unit of Measure',
    )
    project_id = fields.Many2one('project.project', string='Project | المشروع', tracking=True)
    sector_id = fields.Many2one(
        'factory.sector',
        string='Sector | القطاع',
        domain="[('project_id', '=', project_id)]",
    )
    production_id = fields.Many2one(
        'mrp.production',
        string='Production Order | أمر الإنتاج',
        help='Linked manufacturing order if any | أمر الإنتاج المرتبط إن وجد',
    )
    
    cost_per_use = fields.Monetary(
        related='mold_id.cost_per_use',
        string='Cost per Use | تكلفة الاستخدام',
        currency_field='currency_id',
        store=True,
    )
    total_cost = fields.Monetary(
        string='Total Cost | إجمالي التكلفة',
        compute='_compute_total_cost',
        store=True,
        currency_field='currency_id',
    )
    
    state = fields.Selection([
        ('draft', 'Draft | مسودة'),
        ('done', 'Done | منتهي'),
        ('cancelled', 'Cancelled | ملغي'),
    ], string='Status | الحالة', default='draft', tracking=True)
    
    notes = fields.Text(string='Notes | ملاحظات')
    analytic_account_id = fields.Many2one('account.analytic.account', string='Analytic Account | الحساب التحليلي')
    currency_id = fields.Many2one(related='mold_id.currency_id', store=True)
    company_id = fields.Many2one(related='mold_id.company_id', store=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('factory.mold.usage') or 'New'
        return super().create(vals_list)

    @api.depends('cost_per_use', 'use_count')
    def _compute_total_cost(self):
        for rec in self:
            rec.total_cost = rec.cost_per_use * rec.use_count

    @api.onchange('project_id')
    def _onchange_project_id(self):
        if self.project_id and self.sector_id and self.sector_id.project_id != self.project_id:
            self.sector_id = False

    def action_confirm(self):
        self.write({'state': 'done'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset(self):
        self.write({'state': 'draft'})
