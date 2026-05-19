# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class FactoryMold(models.Model):
    """
    Mold | القالب
    
    A mold is a physical reusable asset used to produce manufactured items.
    Each mold has:
    - A manufacturing cost (the cost to build the mold itself)
    - An expected number of uses (lifespan)
    - A tracked actual number of uses
    - An amortized cost per produced unit
    
    القالب أصل مادي قابل لإعادة الاستخدام يُستعمل لإنتاج القطع المصنعة.
    لكل قالب تكلفة تصنيع، وعمر افتراضي بعدد الاستخدامات، ويتم احتساب
    تكلفة القالب الموزعة على كل قطعة منتجة.
    """
    _name = 'factory.mold'
    _description = 'Manufacturing Mold | قالب التصنيع'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char(string='Mold Name | اسم القالب', required=True, tracking=True)
    code = fields.Char(string='Mold Code | كود القالب', required=True, copy=False, default='New', tracking=True)
    category_id = fields.Many2one('factory.mold.category', string='Category | الفئة', tracking=True)
    description = fields.Text(string='Description | الوصف')
    image = fields.Image(string='Image | صورة', max_width=1920, max_height=1920)
    
    # Mold Type | نوع القالب
    mold_type = fields.Selection([
        ('rubber', 'Rubber | مطاط'),
        ('fiberglass', 'Fiberglass | فايبر جلاس'),
        ('steel', 'Steel | حديد'),
        ('wooden', 'Wooden | خشبي'),
        ('silicone', 'Silicone | سيليكون'),
        ('plastic', 'Plastic | بلاستيك'),
        ('concrete', 'Concrete | خرساني'),
        ('other', 'Other | أخرى'),
    ], string='Mold Type | نوع القالب', default='fiberglass', tracking=True)
    
    # Product produced by this mold | المنتج الذي ينتجه هذا القالب
    product_id = fields.Many2one(
        'product.product',
        string='Produced Product | المنتج المنتج',
        domain="[('is_factory_product', '=', True)]",
        tracking=True,
        help='The product produced using this mold | المنتج الذي يُنتج باستخدام هذا القالب',
    )
    output_quantity = fields.Float(
        string='Output per Use | الإنتاج لكل استخدام',
        default=1.0,
        help='Number of products produced per single use of this mold | عدد القطع المنتجة في كل استخدام للقالب',
    )
    
    # Cost & Lifespan | التكلفة والعمر
    manufacturing_cost = fields.Monetary(
        string='Manufacturing Cost | تكلفة التصنيع',
        currency_field='currency_id',
        tracking=True,
        help='Total cost to build this mold | إجمالي تكلفة تصنيع القالب',
    )
    expected_uses = fields.Integer(
        string='Expected Uses | عدد الاستخدامات المتوقع',
        default=50,
        tracking=True,
        help='Expected total uses before retirement | العدد المتوقع للاستخدامات قبل التقاعد',
    )
    actual_uses = fields.Integer(
        string='Actual Uses | الاستخدامات الفعلية',
        compute='_compute_usage_stats',
        store=True,
        tracking=True,
    )
    remaining_uses = fields.Integer(
        string='Remaining Uses | الاستخدامات المتبقية',
        compute='_compute_usage_stats',
        store=True,
    )
    usage_percent = fields.Float(
        string='Usage % | نسبة الاستخدام',
        compute='_compute_usage_stats',
        store=True,
        digits=(5, 2),
    )
    
    # Amortized cost per unit | التكلفة الموزعة لكل وحدة
    cost_per_use = fields.Monetary(
        string='Cost per Use | تكلفة الاستخدام',
        compute='_compute_cost_per_use',
        store=True,
        currency_field='currency_id',
        help='Manufacturing cost ÷ expected uses | تكلفة التصنيع ÷ عدد الاستخدامات المتوقع',
    )
    cost_per_unit = fields.Monetary(
        string='Cost per Unit | تكلفة الوحدة',
        compute='_compute_cost_per_use',
        store=True,
        currency_field='currency_id',
        help='Cost per use ÷ output per use | تكلفة الاستخدام ÷ الإنتاج لكل استخدام',
    )
    cost_consumed = fields.Monetary(
        string='Cost Consumed | التكلفة المستهلكة',
        compute='_compute_cost_per_use',
        store=True,
        currency_field='currency_id',
    )
    cost_remaining = fields.Monetary(
        string='Cost Remaining | التكلفة المتبقية',
        compute='_compute_cost_per_use',
        store=True,
        currency_field='currency_id',
    )
    
    # Amortization Method | طريقة الإهلاك
    amortization_method = fields.Selection([
        ('linear', 'Linear (per use) | خطية (لكل استخدام)'),
        ('quantity', 'By Produced Quantity | حسب الكمية المنتجة'),
        ('time', 'By Time (months) | حسب الوقت (شهور)'),
    ], string='Amortization Method | طريقة الإهلاك',
       default='linear',
       required=True)
    expected_life_months = fields.Integer(
        string='Expected Life (months) | العمر المتوقع (شهور)',
        default=12,
    )
    
    # Lifecycle | دورة الحياة
    construction_date = fields.Date(
        string='Construction Date | تاريخ الإنشاء',
        default=fields.Date.context_today,
        tracking=True,
    )
    first_use_date = fields.Date(
        string='First Use | أول استخدام',
        compute='_compute_usage_stats',
        store=True,
    )
    last_use_date = fields.Date(
        string='Last Use | آخر استخدام',
        compute='_compute_usage_stats',
        store=True,
    )
    retirement_date = fields.Date(string='Retirement Date | تاريخ التقاعد', tracking=True)
    
    # Location | الموقع
    location_id = fields.Many2one(
        'stock.location',
        string='Current Location | الموقع الحالي',
        domain=[('usage', 'in', ['internal', 'view'])],
        tracking=True,
    )
    
    # State | الحالة
    state = fields.Selection([
        ('draft', 'Draft | مسودة'),
        ('manufacturing', 'Manufacturing | تحت التصنيع'),
        ('available', 'Available | متاح'),
        ('in_use', 'In Use | تحت الاستخدام'),
        ('maintenance', 'Maintenance | صيانة'),
        ('retired', 'Retired | متقاعد'),
        ('damaged', 'Damaged | تالف'),
    ], string='Status | الحالة', default='draft', tracking=True)
    
    # Relations | العلاقات
    project_ids = fields.Many2many(
        'project.project',
        'mold_project_rel',
        'mold_id',
        'project_id',
        string='Projects | المشاريع',
        help='Projects this mold has been used for | المشاريع التي تم استخدام القالب فيها',
    )
    sector_ids = fields.Many2many(
        'factory.sector',
        'mold_sector_rel',
        'mold_id',
        'sector_id',
        string='Sectors | القطاعات',
    )
    usage_ids = fields.One2many('factory.mold.usage', 'mold_id', string='Usage History | سجل الاستخدام')
    usage_count = fields.Integer(compute='_compute_usage_count', string='Usage Records | سجلات الاستخدام')
    
    # Accounting | المحاسبة
    asset_account_id = fields.Many2one(
        'account.account',
        string='Asset Account | حساب الأصل',
        help='Asset account where the mold is recorded | حساب الأصل المسجل عليه القالب',
    )
    expense_account_id = fields.Many2one(
        'account.account',
        string='Amortization Expense Account | حساب مصروف الإهلاك',
    )
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account | الحساب التحليلي',
    )
    
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id,
    )
    company_id = fields.Many2one(
        'res.company',
        default=lambda self: self.env.company,
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('code_company_uniq', 'unique(code, company_id)',
         'Mold code must be unique per company! | كود القالب يجب أن يكون فريداً لكل شركة!'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', 'New') == 'New':
                vals['code'] = self.env['ir.sequence'].next_by_code('factory.mold') or 'New'
        return super().create(vals_list)

    @api.depends('usage_ids', 'usage_ids.use_count', 'usage_ids.state')
    def _compute_usage_stats(self):
        for rec in self:
            valid_usages = rec.usage_ids.filtered(lambda u: u.state == 'done')
            rec.actual_uses = sum(valid_usages.mapped('use_count'))
            rec.remaining_uses = max(0, rec.expected_uses - rec.actual_uses)
            rec.usage_percent = (rec.actual_uses / rec.expected_uses * 100.0) if rec.expected_uses else 0.0
            dates = valid_usages.mapped('usage_date')
            rec.first_use_date = min(dates) if dates else False
            rec.last_use_date = max(dates) if dates else False

    @api.depends('manufacturing_cost', 'expected_uses', 'actual_uses', 'output_quantity')
    def _compute_cost_per_use(self):
        for rec in self:
            if rec.expected_uses > 0:
                rec.cost_per_use = rec.manufacturing_cost / rec.expected_uses
            else:
                rec.cost_per_use = 0.0
            rec.cost_per_unit = rec.cost_per_use / rec.output_quantity if rec.output_quantity else 0.0
            rec.cost_consumed = rec.cost_per_use * rec.actual_uses
            rec.cost_remaining = max(0.0, rec.manufacturing_cost - rec.cost_consumed)

    @api.depends('usage_ids')
    def _compute_usage_count(self):
        for rec in self:
            rec.usage_count = len(rec.usage_ids)

    @api.constrains('expected_uses')
    def _check_expected_uses(self):
        for rec in self:
            if rec.expected_uses <= 0:
                raise ValidationError(_('Expected uses must be greater than zero | عدد الاستخدامات المتوقع يجب أن يكون أكبر من صفر'))

    @api.constrains('output_quantity')
    def _check_output_quantity(self):
        for rec in self:
            if rec.output_quantity <= 0:
                raise ValidationError(_('Output per use must be greater than zero | الإنتاج لكل استخدام يجب أن يكون أكبر من صفر'))

    def action_set_manufacturing(self):
        self.write({'state': 'manufacturing'})

    def action_set_available(self):
        self.write({'state': 'available'})

    def action_set_in_use(self):
        self.write({'state': 'in_use'})

    def action_set_maintenance(self):
        self.write({'state': 'maintenance'})

    def action_retire(self):
        self.write({'state': 'retired', 'retirement_date': fields.Date.context_today(self)})

    def action_view_usages(self):
        self.ensure_one()
        return {
            'name': _('Usage History | سجل الاستخدام'),
            'type': 'ir.actions.act_window',
            'res_model': 'factory.mold.usage',
            'view_mode': 'list,form',
            'domain': [('mold_id', '=', self.id)],
            'context': {'default_mold_id': self.id},
        }

    def register_usage(self, project_id=None, sector_id=None, use_count=1, produced_qty=0.0, notes=''):
        """
        Convenience method to register a mold usage from external modules.
        طريقة مختصرة لتسجيل استخدام للقالب من موديولات أخرى.
        """
        self.ensure_one()
        return self.env['factory.mold.usage'].create({
            'mold_id': self.id,
            'project_id': project_id,
            'sector_id': sector_id,
            'use_count': use_count,
            'produced_quantity': produced_qty,
            'notes': notes,
            'state': 'done',
        })
