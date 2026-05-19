# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class FactoryMix(models.Model):
    """
    Mix Design (Recipe) | تصميم الخلطة (الوصفة)
    
    A mix design defines the raw material proportions needed to produce
    a unit of a finished product. Multiple mixes can exist for the same
    product, varying by:
    - Strength requirements (المقاومة)
    - Weight (الوزن)
    - Finishing type (التشطيب)
    - Element nature (طبيعة العنصر)
    - Site conditions (ظروف الموقع)
    
    تعريف نسب الخامات اللازمة لإنتاج وحدة من المنتج النهائي.
    قد توجد خلطات متعددة لنفس المنتج تختلف حسب: المقاومة، الوزن، نوع التشطيب،
    طبيعة العنصر، وظروف الموقع.
    """
    _name = 'factory.mix'
    _description = 'Mix Design / Recipe | تصميم الخلطة'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'product_id, version desc, name'

    name = fields.Char(string='Mix Name | اسم الخلطة', required=True, tracking=True)
    code = fields.Char(string='Code | الكود', required=True, copy=False, default='New', tracking=True)
    version = fields.Char(string='Version | الإصدار', default='1.0', tracking=True)
    
    product_id = fields.Many2one(
        'product.product',
        string='Product | المنتج',
        required=True,
        domain="[('is_factory_product', '=', True)]",
        tracking=True,
        help='Finished product produced by this mix | المنتج النهائي الذي تنتجه هذه الخلطة',
    )
    output_quantity = fields.Float(
        string='Output Quantity | كمية الإنتاج',
        default=1.0,
        required=True,
        digits='Product Unit of Measure',
        help='Quantity produced by 1 batch of this mix | الكمية المنتجة من دفعة واحدة من هذه الخلطة',
    )
    output_uom_id = fields.Many2one(
        'uom.uom',
        string='Output UoM | وحدة الإنتاج',
        related='product_id.uom_id',
        store=True,
        readonly=True,
    )
    
    # Mix characteristics | خصائص الخلطة
    strength_class = fields.Char(string='Strength Class | درجة المقاومة')
    target_weight = fields.Float(string='Target Weight (kg) | الوزن المستهدف (كجم)')
    finishing_type = fields.Char(string='Finishing Type | نوع التشطيب')
    description = fields.Text(string='Description / Notes | الوصف / ملاحظات')
    
    # Lines (raw materials) | البنود (الخامات)
    line_ids = fields.One2many('factory.mix.line', 'mix_id', string='Materials | الخامات', copy=True)
    
    # Cost rollup | تجميع التكلفة
    total_material_cost = fields.Monetary(
        string='Total Material Cost | إجمالي تكلفة الخامات',
        compute='_compute_costs',
        store=True,
        currency_field='currency_id',
        help='Sum of all material costs in this mix | مجموع تكاليف كل الخامات في هذه الخلطة',
    )
    cost_per_unit = fields.Monetary(
        string='Cost per Unit | تكلفة الوحدة',
        compute='_compute_costs',
        store=True,
        currency_field='currency_id',
        help='Total material cost ÷ output quantity | إجمالي تكلفة الخامات ÷ كمية الإنتاج',
    )
    total_waste_percent = fields.Float(
        string='Total Waste % | نسبة الهالك الإجمالية',
        compute='_compute_costs',
        store=True,
        digits=(5, 2),
    )
    
    # State | الحالة
    state = fields.Selection([
        ('draft', 'Draft | مسودة'),
        ('approved', 'Approved | معتمد'),
        ('obsolete', 'Obsolete | متوقف'),
    ], string='Status | الحالة', default='draft', tracking=True)
    
    # Usage tracking | تتبع الاستخدام
    sector_count = fields.Integer(compute='_compute_sector_count', string='Sectors Using | قطاعات تستخدمها')
    
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id,
    )
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('code_company_uniq', 'unique(code, company_id)',
         'Mix code must be unique per company! | كود الخلطة يجب أن يكون فريداً لكل شركة!'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', 'New') == 'New':
                vals['code'] = self.env['ir.sequence'].next_by_code('factory.mix') or 'New'
        return super().create(vals_list)

    @api.depends('line_ids', 'line_ids.total_cost', 'line_ids.waste_percent', 'output_quantity')
    def _compute_costs(self):
        for rec in self:
            rec.total_material_cost = sum(rec.line_ids.mapped('total_cost'))
            rec.cost_per_unit = rec.total_material_cost / rec.output_quantity if rec.output_quantity else 0.0
            # weighted-average waste percent based on cost
            total = sum(rec.line_ids.mapped('total_cost'))
            if total > 0:
                weighted = sum(l.total_cost * l.waste_percent for l in rec.line_ids)
                rec.total_waste_percent = weighted / total
            else:
                rec.total_waste_percent = 0.0

    def _compute_sector_count(self):
        for rec in self:
            rec.sector_count = self.env['factory.sector'].search_count([('mix_id', '=', rec.id)])

    @api.constrains('output_quantity')
    def _check_output_quantity(self):
        for rec in self:
            if rec.output_quantity <= 0:
                raise ValidationError(_('Output quantity must be greater than zero | كمية الإنتاج يجب أن تكون أكبر من صفر'))

    def action_approve(self):
        for rec in self:
            if not rec.line_ids:
                raise ValidationError(_('Cannot approve a mix with no materials | لا يمكن اعتماد خلطة بدون خامات'))
            rec.state = 'approved'

    def action_obsolete(self):
        self.write({'state': 'obsolete'})

    def action_reset_to_draft(self):
        self.write({'state': 'draft'})

    def action_view_sectors(self):
        self.ensure_one()
        return {
            'name': _('Sectors Using This Mix | قطاعات تستخدم هذه الخلطة'),
            'type': 'ir.actions.act_window',
            'res_model': 'factory.sector',
            'view_mode': 'list,form',
            'domain': [('mix_id', '=', self.id)],
        }

    def copy(self, default=None):
        default = dict(default or {})
        if 'code' not in default:
            default['code'] = 'New'
        if 'name' not in default:
            default['name'] = _('%s (Copy)') % self.name
        if 'state' not in default:
            default['state'] = 'draft'
        return super().copy(default)
