# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools.safe_eval import safe_eval


class AccessRightGroup(models.Model):
    _name = 'access.right.group'
    _description = 'Access Right Group'
    _order = 'name, id'

    name = fields.Char(required=True, translate=False)
    active = fields.Boolean(default=True)
    note = fields.Text()

    user_ids = fields.Many2many(
        'res.users',
        'access_right_group_user_rel',
        'group_id',
        'user_id',
        string='Users',
    )

    field_rule_ids = fields.One2many(
        'access.right.group.field.line',
        'group_id',
        string='Field Restrictions',
    )
    hidden_menu_line_ids = fields.One2many(
        'access.right.group.menu.line',
        'group_id',
        string='Hidden Menus',
    )
    model_rule_ids = fields.One2many(
        'access.right.group.model.line',
        'group_id',
        string='Model Restrictions',
    )
    button_rule_ids = fields.One2many(
        'access.right.group.button.line',
        'group_id',
        string='Button Restrictions',
    )
    conditional_rule_ids = fields.One2many(
        'access.right.group.condition.line',
        'group_id',
        string='Conditional Access Rules',
    )

    warehouse_ids = fields.Many2many(
        'stock.warehouse',
        'access_right_group_warehouse_rel',
        'group_id',
        'warehouse_id',
        string='Warehouses',
    )
    location_ids = fields.Many2many(
        'stock.location',
        'access_right_group_location_rel',
        'group_id',
        'location_id',
        string='Locations',
    )
    picking_type_ids = fields.Many2many(
        'stock.picking.type',
        'access_right_group_picking_type_rel',
        'group_id',
        'picking_type_id',
        string='Operation Types',
    )

    product_ids = fields.Many2many(
        'product.product',
        'access_right_group_product_rel',
        'group_id',
        'product_id',
        string='Allowed Products',
    )
    product_tmpl_ids = fields.Many2many(
        'product.template',
        'access_right_group_product_tmpl_rel',
        'group_id',
        'product_tmpl_id',
        string='Allowed Product Templates',
    )
    product_categ_ids = fields.Many2many(
        'product.category',
        'access_right_group_product_categ_rel',
        'group_id',
        'categ_id',
        string='Allowed Product Categories',
    )
    product_tag_ids = fields.Many2many(
        'product.tag',
        'access_right_group_product_tag_rel',
        'group_id',
        'tag_id',
        string='Allowed Product Tags',
    )

    partner_salesperson_id = fields.Many2one('res.users', string='Salesperson')
    partner_ids = fields.Many2many(
        'res.partner',
        'access_right_group_partner_rel',
        'group_id',
        'partner_id',
        string='Allowed Partners',
    )
    partner_category_ids = fields.Many2many(
        'res.partner.category',
        'access_right_group_partner_category_rel',
        'group_id',
        'category_id',
        string='Allowed Partner Tags',
    )
    partner_type = fields.Selection(
        [
            ('both', 'Customers and Vendors'),
            ('customer', 'Customers Only'),
            ('vendor', 'Vendors Only'),
        ],
        default='both',
        required=True,
        string='Partner Type',
    )

    journal_ids = fields.Many2many(
        'account.journal',
        'access_right_group_journal_rel',
        'group_id',
        'journal_id',
        string='Allowed Journals',
    )
    blocked_account_ids = fields.Many2many(
        'account.account',
        'access_right_group_account_rel',
        'group_id',
        'account_id',
        string='Blocked Accounts',
    )

    is_responsible = fields.Boolean()
    no_quick_create = fields.Boolean()
    no_hyperlink = fields.Boolean(string='Disable Hyperlinks')
    hide_bom = fields.Boolean()
    readonly_bom = fields.Boolean()

    @api.model
    def _runtime_excluded_models(self):
        return {
            'access.right.group',
            'access.right.group.field.line',
            'access.right.group.menu.line',
            'access.right.group.model.line',
            'access.right.group.model.page',
            'access.right.group.button.line',
            'access.right.group.condition.line',
            'ir.model',
            'ir.model.fields',
            'ir.rule',
            'ir.ui.view',
            'ir.model.data',
        }

    @api.model
    def _runtime_active(self):
        registry_ready = getattr(self.env.registry, 'ready', True)
        return bool(
            registry_ready
            and not self.env.su
            and self.env.uid != 1
            and not self.env.context.get('access_right_management_bypass')
        )

    @api.model
    def _get_current_user_groups(self):
        if not self._runtime_active():
            return self.browse()
        return self.sudo().search([
            ('active', '=', True),
            ('user_ids', 'in', [self.env.uid]),
        ])

    @api.model
    def _clear_runtime_caches(self):
        self.env.registry.clear_cache()
        for model_name in ('ir.ui.view', 'ir.ui.menu', 'access.right.group'):
            model = self.env[model_name]
            for candidate in ('clear_caches', 'clear_cache', '_clear_cache'):
                method = getattr(model, candidate, None)
                if method:
                    method()
                    break

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self._clear_runtime_caches()
        return records

    def write(self, vals):
        res = super().write(vals)
        self._clear_runtime_caches()
        return res

    def unlink(self):
        res = super().unlink()
        self._clear_runtime_caches()
        return res


class AccessRightGroupFieldLine(models.Model):
    _name = 'access.right.group.field.line'
    _description = 'Access Right Field Restriction'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)
    group_id = fields.Many2one('access.right.group', required=True, ondelete='cascade')
    model_id = fields.Many2one('ir.model', required=True, ondelete='cascade')
    model_model = fields.Char(related='model_id.model', store=True, readonly=True)
    field_id = fields.Many2one(
        'ir.model.fields',
        required=True,
        domain="[('model_id', '=', model_id)]",
        ondelete='cascade',
    )
    hide_field = fields.Boolean()
    required_field = fields.Boolean()
    readonly_field = fields.Boolean()

    @api.onchange('model_id')
    def _onchange_model_id(self):
        self.field_id = False

    @api.constrains('model_id', 'field_id')
    def _check_field_model(self):
        for line in self:
            if line.field_id and line.field_id.model_id != line.model_id:
                raise ValidationError(_('The selected field must belong to the selected model.'))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self.env['access.right.group']._clear_runtime_caches()
        return records

    def write(self, vals):
        res = super().write(vals)
        self.env['access.right.group']._clear_runtime_caches()
        return res

    def unlink(self):
        res = super().unlink()
        self.env['access.right.group']._clear_runtime_caches()
        return res


class AccessRightGroupMenuLine(models.Model):
    _name = 'access.right.group.menu.line'
    _description = 'Access Right Hidden Menu'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)
    group_id = fields.Many2one('access.right.group', required=True, ondelete='cascade')
    menu_id = fields.Many2one('ir.ui.menu', required=True, ondelete='cascade')

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self.env['access.right.group']._clear_runtime_caches()
        return records

    def write(self, vals):
        res = super().write(vals)
        self.env['access.right.group']._clear_runtime_caches()
        return res

    def unlink(self):
        res = super().unlink()
        self.env['access.right.group']._clear_runtime_caches()
        return res


class AccessRightGroupModelLine(models.Model):
    _name = 'access.right.group.model.line'
    _description = 'Access Right Model Restriction'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)
    group_id = fields.Many2one('access.right.group', required=True, ondelete='cascade')
    model_id = fields.Many2one('ir.model', required=True, ondelete='cascade')
    model_model = fields.Char(related='model_id.model', store=True, readonly=True)
    allow_read = fields.Boolean(default=True)
    allow_write = fields.Boolean(default=True)
    allow_create = fields.Boolean(default=True)
    allow_unlink = fields.Boolean(default=True)
    page_rule_ids = fields.One2many(
        'access.right.group.model.page',
        'model_rule_id',
        string='Hidden Tabs',
    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self.env['access.right.group']._clear_runtime_caches()
        return records

    def write(self, vals):
        res = super().write(vals)
        self.env['access.right.group']._clear_runtime_caches()
        return res

    def unlink(self):
        res = super().unlink()
        self.env['access.right.group']._clear_runtime_caches()
        return res


class AccessRightGroupModelPage(models.Model):
    _name = 'access.right.group.model.page'
    _description = 'Access Right Hidden Model Tab'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)
    model_rule_id = fields.Many2one('access.right.group.model.line', required=True, ondelete='cascade')
    group_id = fields.Many2one(related='model_rule_id.group_id', store=True, readonly=True)
    model_id = fields.Many2one(related='model_rule_id.model_id', store=True, readonly=True)
    view_id = fields.Many2one(
        'ir.ui.view',
        string='Form View',
        domain="[('model', '=', model_rule_id.model_model), ('type', '=', 'form')]",
        ondelete='cascade',
    )
    page_name = fields.Char(
        string='Page Technical Name',
        help="Matches the notebook page 'name' attribute.",
    )
    page_string = fields.Char(
        string='Page Label',
        help="Matches the notebook page displayed title.",
    )

    @api.constrains('page_name', 'page_string')
    def _check_page_identifier(self):
        for line in self:
            if not line.page_name and not line.page_string:
                raise ValidationError(_('Please define a page technical name or a page label.'))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self.env['access.right.group']._clear_runtime_caches()
        return records

    def write(self, vals):
        res = super().write(vals)
        self.env['access.right.group']._clear_runtime_caches()
        return res

    def unlink(self):
        res = super().unlink()
        self.env['access.right.group']._clear_runtime_caches()
        return res


class AccessRightGroupConditionLine(models.Model):
    _name = 'access.right.group.condition.line'
    _description = 'Access Right Conditional Deny Rule'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)
    group_id = fields.Many2one('access.right.group', required=True, ondelete='cascade')
    model_id = fields.Many2one('ir.model', required=True, ondelete='cascade')
    model_model = fields.Char(related='model_id.model', store=True, readonly=True)
    domain_force = fields.Char(required=True, string='Denied Domain')

    @api.constrains('domain_force', 'model_id')
    def _check_domain_force(self):
        for line in self:
            if not line.domain_force:
                continue
            try:
                eval_context = self.env['ir.rule']._eval_context()
                domain = safe_eval(line.domain_force, eval_context)
                if not isinstance(domain, (list, tuple)):
                    raise ValidationError(_('The denied domain must be a valid domain expression.'))
                self.env[line.model_model].with_context(access_right_management_bypass=True)._search(domain, limit=1)
            except ValidationError:
                raise
            except Exception as err:
                raise ValidationError(_('Invalid domain for model %s: %s') % (line.model_model, err))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self.env['access.right.group']._clear_runtime_caches()
        return records

    def write(self, vals):
        res = super().write(vals)
        self.env['access.right.group']._clear_runtime_caches()
        return res

    def unlink(self):
        res = super().unlink()
        self.env['access.right.group']._clear_runtime_caches()
        return res


class AccessRightGroupButtonLine(models.Model):
    _name = 'access.right.group.button.line'
    _description = 'Access Right Button Restriction'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)
    group_id = fields.Many2one('access.right.group', required=True, ondelete='cascade')
    model_id = fields.Many2one('ir.model', required=True, ondelete='cascade')
    model_model = fields.Char(related='model_id.model', store=True, readonly=True)
    view_id = fields.Many2one(
        'ir.ui.view',
        string='View',
        domain="[('model', '=', model_model)]",
        ondelete='cascade',
        help='Optional. Leave empty to apply on all views of the selected model.',
    )
    button_name = fields.Char(
        string='Button Technical Name',
        help="Matches the button 'name' attribute in the XML view.",
    )
    button_label = fields.Char(
        string='Button Label',
        help="Matches the button 'string' attribute in the XML view.",
    )
    button_type = fields.Selection(
        [
            ('', 'Any'),
            ('object', 'Object'),
            ('action', 'Action'),
        ],
        string='Button Type',
        default='',
    )
    hide_button = fields.Boolean(default=True)

    @api.constrains('button_name', 'button_label')
    def _check_button_identifier(self):
        for line in self:
            if not line.button_name and not line.button_label:
                raise ValidationError(_('Please define a button technical name or a button label.'))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self.env['access.right.group']._clear_runtime_caches()
        return records

    def write(self, vals):
        res = super().write(vals)
        self.env['access.right.group']._clear_runtime_caches()
        return res

    def unlink(self):
        res = super().unlink()
        self.env['access.right.group']._clear_runtime_caches()
        return res


class ResUsers(models.Model):
    _inherit = 'res.users'

    access_right_group_ids = fields.Many2many(
        'access.right.group',
        compute='_compute_access_right_group_ids',
        string='Access Right Groups',
    )
    access_right_is_responsible = fields.Boolean(
        compute='_compute_access_right_group_ids',
        string='Is Responsible',
    )

    def _compute_access_right_group_ids(self):
        group_model = self.env['access.right.group'].sudo()
        for user in self:
            groups = group_model.search([('active', '=', True), ('user_ids', 'in', [user.id])])
            user.access_right_group_ids = groups
            user.access_right_is_responsible = any(groups.mapped('is_responsible'))
