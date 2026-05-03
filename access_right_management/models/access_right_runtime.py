# -*- coding: utf-8 -*-

import json
import logging
from functools import reduce

from lxml import etree

from odoo import _, api, models, tools
from odoo.exceptions import AccessError, ValidationError
from odoo.osv import expression
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)


class AccessRightRuntimeBase(models.AbstractModel):
    _inherit = 'base'

    @api.model
    def _arm_groups(self):
        return self.env['access.right.group']._get_current_user_groups()

    @api.model
    def _arm_runtime_enabled(self):
        group_model = self.env['access.right.group']
        return (
            self._name not in group_model._runtime_excluded_models()
            and group_model._runtime_active()
        )

    @api.model
    def _arm_or_domains(self, domains):
        clean_domains = [domain for domain in domains if domain]
        if not clean_domains:
            return []
        return reduce(lambda left, right: expression.OR([left, right]), clean_domains[1:], clean_domains[0])

    @api.model
    def _arm_eval_domain(self, domain_force):
        eval_context = self.env['ir.rule']._eval_context()
        domain = safe_eval(domain_force or '[]', eval_context)
        return list(domain or [])

    @api.model
    def _arm_has_tag_field(self, model_name):
        model = self.env[model_name]
        for field_name in ('product_tag_ids', 'tag_ids'):
            if field_name in model._fields:
                return field_name
        return False

    @api.model
    def _arm_collect_denied_domains(self, groups):
        denied_domains = []
        condition_lines = groups.conditional_rule_ids.filtered(lambda line: line.model_model == self._name and line.domain_force)
        for line in condition_lines:
            try:
                denied_domains.append(self._arm_eval_domain(line.domain_force))
            except Exception as err:
                _logger.warning("Skipping invalid denied domain on %s: %s", line.display_name, err)
        return denied_domains

    @api.model
    def _arm_model_specific_domain(self, groups):
        if not groups:
            return []

        model_name = self._name
        domains = []

        if model_name == 'ir.ui.menu':
            hidden_menu_ids = groups.hidden_menu_line_ids.mapped('menu_id').ids
            if hidden_menu_ids:
                domains.append([('id', 'not in', hidden_menu_ids)])

        if model_name == 'stock.warehouse':
            warehouse_ids = groups.mapped('warehouse_ids').ids
            if warehouse_ids:
                domains.append([('id', 'in', warehouse_ids)])

        if model_name == 'stock.location':
            location_ids = groups.mapped('location_ids').ids
            if location_ids:
                domains.append([('id', 'in', location_ids)])

        if model_name == 'stock.picking.type':
            picking_type_ids = groups.mapped('picking_type_ids').ids
            if picking_type_ids:
                domains.append([('id', 'in', picking_type_ids)])

        if model_name in ('product.product', 'product.template'):
            tag_field = self._arm_has_tag_field(model_name)
            has_product_filter = any(
                group.product_ids
                or group.product_tmpl_ids
                or group.product_categ_ids
                or group.product_tag_ids
                for group in groups
            )
            if has_product_filter:
                product_domains = []
                product_ids = groups.mapped('product_ids').ids
                product_tmpl_ids = groups.mapped('product_tmpl_ids').ids
                categ_ids = groups.mapped('product_categ_ids').ids
                tag_ids = groups.mapped('product_tag_ids').ids
                if model_name == 'product.product':
                    if product_ids:
                        product_domains.append([('id', 'in', product_ids)])
                    if product_tmpl_ids:
                        product_domains.append([('product_tmpl_id', 'in', product_tmpl_ids)])
                    if categ_ids:
                        product_domains.append([('product_tmpl_id.categ_id', 'in', categ_ids)])
                    if tag_ids and tag_field:
                        product_domains.append([('product_tmpl_id.%s' % tag_field, 'in', tag_ids)])
                else:
                    if product_ids:
                        product_domains.append([('product_variant_ids', 'in', product_ids)])
                    if product_tmpl_ids:
                        product_domains.append([('id', 'in', product_tmpl_ids)])
                    if categ_ids:
                        product_domains.append([('categ_id', 'in', categ_ids)])
                    if tag_ids and tag_field:
                        product_domains.append([(tag_field, 'in', tag_ids)])
                combined_product_domain = self._arm_or_domains(product_domains)
                if combined_product_domain:
                    domains.append(combined_product_domain)

        if model_name == 'res.partner':
            has_partner_filter = any(
                group.partner_salesperson_id
                or group.partner_ids
                or group.partner_category_ids
                or group.partner_type != 'both'
                for group in groups
            )
            if has_partner_filter:
                partner_domains = []
                salesperson_ids = groups.mapped('partner_salesperson_id').ids
                partner_ids = groups.mapped('partner_ids').ids
                category_ids = groups.mapped('partner_category_ids').ids
                selected_types = {group.partner_type for group in groups if group.partner_type and group.partner_type != 'both'}
                if salesperson_ids:
                    partner_domains.append([('user_id', 'in', salesperson_ids)])
                if partner_ids:
                    partner_domains.append([('id', 'in', partner_ids)])
                if category_ids:
                    partner_domains.append([('category_id', 'in', category_ids)])
                if 'customer' in selected_types:
                    partner_domains.append([('customer_rank', '>', 0)])
                if 'vendor' in selected_types:
                    partner_domains.append([('supplier_rank', '>', 0)])
                combined_partner_domain = self._arm_or_domains(partner_domains)
                if combined_partner_domain:
                    domains.append(combined_partner_domain)

        if model_name == 'account.journal':
            journal_ids = groups.mapped('journal_ids').ids
            if journal_ids:
                domains.append([('id', 'in', journal_ids)])

        if model_name == 'account.account':
            blocked_account_ids = groups.mapped('blocked_account_ids').ids
            if blocked_account_ids:
                domains.append([('id', 'not in', blocked_account_ids)])

        return expression.AND(domains) if domains else []

    @api.model
    def _arm_access_denied_by_model_rule(self, operation, groups):
        operation_field = {
            'read': 'allow_read',
            'write': 'allow_write',
            'create': 'allow_create',
            'unlink': 'allow_unlink',
        }.get(operation)
        if not operation_field:
            return False
        rules = groups.model_rule_ids.filtered(lambda line: line.model_model == self._name)
        return bool(rules and any(not getattr(rule, operation_field) for rule in rules))

    @api.model
    def _arm_requires_bom_readonly(self, operation):
        return self._name in ('mrp.bom', 'mrp.bom.line', 'mrp.production') and operation in ('create', 'write', 'unlink')

    @api.model
    def _arm_check_extra_access_rights(self, operation):
        if not self._arm_runtime_enabled():
            return
        groups = self._arm_groups()
        if not groups:
            return

        if self._arm_access_denied_by_model_rule(operation, groups):
            raise AccessError(_("Access to model '%s' is denied for operation '%s'.") % (self._name, operation))

        if self._arm_requires_bom_readonly(operation) and any(groups.mapped('readonly_bom')):
            raise AccessError(_("Bill of Materials and Manufacturing Orders are readonly for your access group."))

    @api.model
    def _arm_get_read_domain(self):
        if not self._arm_runtime_enabled():
            return []
        groups = self._arm_groups()
        if not groups:
            return []
        if self._arm_access_denied_by_model_rule('read', groups):
            return [('id', '=', 0)]

        domains = []
        model_domain = self._arm_model_specific_domain(groups)
        if model_domain:
            domains.append(model_domain)

        denied_domains = self._arm_collect_denied_domains(groups)
        for denied_domain in denied_domains:
            domains.append(['!'] + denied_domain)

        return expression.AND(domains) if domains else []

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None, **kwargs):
        if self._arm_runtime_enabled():
            read_domain = self._arm_get_read_domain()
            if read_domain:
                domain = expression.AND([domain or [], read_domain])
        return super()._search(domain, offset=offset, limit=limit, order=order, **kwargs)

    @api.model
    def _name_search(self, name='', domain=None, operator='ilike', limit=None, order=None, **kwargs):
        if self._arm_runtime_enabled():
            read_domain = self._arm_get_read_domain()
            if read_domain:
                domain = expression.AND([domain or [], read_domain])
        return super()._name_search(name=name, domain=domain, operator=operator, limit=limit, order=order, **kwargs)

    def check_access_rights(self, operation, raise_exception=True):
        result = super().check_access_rights(operation, raise_exception=raise_exception)
        try:
            self._arm_check_extra_access_rights(operation)
        except AccessError:
            if raise_exception:
                raise
            return False
        return result

    def check_access_rule(self, operation):
        result = super().check_access_rule(operation)
        if not self or not self._arm_runtime_enabled():
            return result

        if operation == 'create':
            return result

        read_domain = self._arm_get_read_domain()
        if read_domain == [('id', '=', 0)]:
            raise AccessError(_("Access to these records is denied by Access Right Management."))
        if read_domain:
            allowed_records = self.filtered_domain(read_domain)
            denied_records = self - allowed_records
            if denied_records:
                raise AccessError(_("Access to one or more records is denied by Access Right Management."))
        return result

    @api.model_create_multi
    def create(self, vals_list):
        self.check_access_rights('create')
        self._arm_validate_blocked_account_values(vals_list)
        records = super().create(vals_list)
        if records and records._arm_runtime_enabled():
            records.check_access_rule('read')
        return records

    def write(self, vals):
        self.check_access_rights('write')
        self.check_access_rule('write')
        self._arm_validate_blocked_account_values([vals])
        return super().write(vals)

    def unlink(self):
        self.check_access_rights('unlink')
        self.check_access_rule('unlink')
        return super().unlink()

    def _arm_validate_blocked_account_values(self, vals_list):
        if not self._arm_runtime_enabled():
            return
        groups = self._arm_groups()
        blocked_account_ids = set(groups.mapped('blocked_account_ids').ids)
        if not blocked_account_ids:
            return

        field_map = {
            name: field for name, field in self._fields.items()
            if field.type in ('many2one', 'many2many', 'one2many') and getattr(field, 'comodel_name', False) == 'account.account'
        }
        if not field_map:
            return

        for vals in vals_list:
            for field_name in field_map:
                if field_name not in vals:
                    continue
                value = vals[field_name]
                ids_to_check = set()
                if isinstance(value, int):
                    ids_to_check.add(value)
                elif isinstance(value, list):
                    for command in value:
                        if not isinstance(command, (list, tuple)) or not command:
                            continue
                        if command[0] == 6:
                            ids_to_check.update(command[2] or [])
                        elif command[0] == 4:
                            ids_to_check.add(command[1])
                        elif command[0] == 0 and isinstance(command[2], dict):
                            nested_vals = command[2]
                            for nested_field_name, nested_field in self.env[self._fields[field_name].comodel_name]._fields.items():
                                if getattr(nested_field, 'comodel_name', False) == 'account.account' and nested_field_name in nested_vals:
                                    nested_value = nested_vals[nested_field_name]
                                    if isinstance(nested_value, int):
                                        ids_to_check.add(nested_value)
                if ids_to_check & blocked_account_ids:
                    raise ValidationError(_("One or more selected accounts are blocked for your access group."))

    @api.model
    def get_view(self, view_id=None, view_type='form', **options):
        result = super().get_view(view_id=view_id, view_type=view_type, **options)
        return self.env['access.right.group']._apply_view_runtime_restrictions(self, result, view_type=view_type)


class AccessRightGroupViewEngine(models.Model):
    _inherit = 'access.right.group'

    @api.model
    def _merge_json_options(self, node, extra_options):
        options = {}
        raw_options = node.get('options')
        if raw_options:
            try:
                options = json.loads(raw_options)
            except Exception:
                try:
                    options = safe_eval(raw_options, {}) or {}
                except Exception:
                    options = {}
        options.update(extra_options)
        node.set('options', json.dumps(options))

    @api.model
    def _set_modifier(self, node, key, value=True):
        modifiers = {}
        raw_modifiers = node.get('modifiers')
        if raw_modifiers:
            try:
                modifiers = json.loads(raw_modifiers)
            except Exception:
                try:
                    modifiers = safe_eval(raw_modifiers, {}) or {}
                except Exception:
                    modifiers = {}
        modifiers[key] = value
        node.set('modifiers', json.dumps(modifiers))

    @api.model
    def _apply_node_boolean(self, node, attribute, value='1'):
        node.set(attribute, value)
        self._set_modifier(node, attribute, value in ('1', 1, True))

    @api.model
    def _collect_field_restrictions(self, groups, model_name):
        restrictions = {}
        for line in groups.field_rule_ids.filtered(lambda field_line: field_line.model_model == model_name):
            field_name = line.field_id.name
            restrictions.setdefault(field_name, {'hide': False, 'readonly': False, 'required': False})
            restrictions[field_name]['hide'] = restrictions[field_name]['hide'] or line.hide_field
            restrictions[field_name]['readonly'] = restrictions[field_name]['readonly'] or line.readonly_field
            restrictions[field_name]['required'] = restrictions[field_name]['required'] or line.required_field
        return restrictions

    @api.model
    def _collect_hidden_pages(self, groups, model_name):
        page_names = set()
        page_labels = set()
        model_rules = groups.model_rule_ids.filtered(lambda rule: rule.model_model == model_name)
        for page_rule in model_rules.mapped('page_rule_ids'):
            if page_rule.page_name:
                page_names.add(page_rule.page_name)
            if page_rule.page_string:
                page_labels.add(page_rule.page_string)
        return page_names, page_labels

    @api.model
    def _collect_hidden_buttons(self, groups, model_name, view_id=None):
        button_rules = groups.button_rule_ids.filtered(
            lambda line: line.model_model == model_name and line.hide_button and (not line.view_id or line.view_id.id == view_id)
        )
        return button_rules

    @api.model
    def _apply_view_runtime_restrictions(self, model, result, view_type='form'):
        if not result or not self._runtime_active():
            return result
        if model._name in self._runtime_excluded_models():
            return result

        groups = self._get_current_user_groups()
        if not groups:
            return result

        arch = result.get('arch')
        if not arch:
            return result

        parser = etree.XMLParser(remove_blank_text=False, recover=True)
        doc = etree.fromstring(arch.encode('utf-8') if isinstance(arch, str) else arch, parser=parser)

        field_restrictions = self._collect_field_restrictions(groups, model._name)
        hidden_page_names, hidden_page_labels = self._collect_hidden_pages(groups, model._name)
        hidden_buttons = self._collect_hidden_buttons(groups, model._name, view_id=result.get('id'))
        no_quick_create = any(groups.mapped('no_quick_create'))
        no_hyperlink = any(groups.mapped('no_hyperlink'))
        hide_bom = any(groups.mapped('hide_bom'))
        readonly_bom = any(groups.mapped('readonly_bom'))

        if no_quick_create:
            for field_node in doc.xpath("//field"):
                if field_node.get('widget') == 'many2one' or field_node.get('name') in model._fields and getattr(model._fields[field_node.get('name')], 'type', None) == 'many2one':
                    self._merge_json_options(field_node, {
                        'no_create': True,
                        'no_create_edit': True,
                        'no_quick_create': True,
                    })

        if no_hyperlink:
            for field_node in doc.xpath("//field"):
                field_name = field_node.get('name')
                field = model._fields.get(field_name) if field_name else None
                field_type = getattr(field, 'type', None)
                widget = field_node.get('widget')

                if field_type in ('many2one', 'many2many', 'one2many', 'reference') or widget in (
                    'many2one',
                    'many2many_tags',
                    'many2one_avatar',
                    'many2one_avatar_user',
                    'reference',
                ):
                    self._merge_json_options(field_node, {
                        'no_open': True,
                        'no_create': True,
                        'no_create_edit': True,
                        'no_quick_create': True,
                    })

                if widget in ('url', 'email', 'phone'):
                    field_node.attrib.pop('widget', None)

        for field_name, flags in field_restrictions.items():
            for field_node in doc.xpath("//field[@name='%s']" % field_name):
                if flags['hide']:
                    if view_type in ('tree', 'list'):
                        self._apply_node_boolean(field_node, 'column_invisible')
                    self._apply_node_boolean(field_node, 'invisible')
                if flags['readonly']:
                    self._apply_node_boolean(field_node, 'readonly')
                if flags['required'] and not flags['hide']:
                    self._apply_node_boolean(field_node, 'required')

        if hidden_page_names or hidden_page_labels:
            for page_node in doc.xpath("//page"):
                if page_node.get('name') in hidden_page_names or page_node.get('string') in hidden_page_labels:
                    self._apply_node_boolean(page_node, 'invisible')

        if hidden_buttons:
            for button_node in doc.xpath("//button"):
                button_name = button_node.get('name')
                button_label = button_node.get('string')
                button_type = button_node.get('type') or ''
                for rule in hidden_buttons:
                    type_matches = not rule.button_type or rule.button_type == button_type
                    name_matches = bool(rule.button_name and rule.button_name == button_name)
                    label_matches = bool(rule.button_label and rule.button_label == button_label)
                    if type_matches and (name_matches or label_matches):
                        self._apply_node_boolean(button_node, 'invisible')
                        break

        if model._name in ('mrp.bom', 'mrp.production'):
            target_field_names = []
            if model._name == 'mrp.bom':
                target_field_names = ['bom_line_ids']
            if model._name == 'mrp.production':
                target_field_names = ['move_raw_ids']

            if hide_bom:
                for field_name in target_field_names:
                    for field_node in doc.xpath("//field[@name='%s']" % field_name):
                        self._apply_node_boolean(field_node, 'invisible')
                        if view_type in ('tree', 'list'):
                            self._apply_node_boolean(field_node, 'column_invisible')

            if readonly_bom:
                for root_node in doc.xpath("/*"):
                    root_node.set('create', '0')
                    root_node.set('edit', '0')
                    root_node.set('delete', '0')
                for field_name in target_field_names:
                    for field_node in doc.xpath("//field[@name='%s']" % field_name):
                        self._apply_node_boolean(field_node, 'readonly')

        result['arch'] = etree.tostring(doc, encoding='unicode')
        return result


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    @api.model
    def _arm_hidden_menu_ids(self):
        group_model = self.env['access.right.group']
        active = group_model._runtime_active()
        _logger.debug("ARM: Checking hidden menus. Runtime active: %s, User: %s", active, self.env.uid)
        
        if not active:
            return set()

        groups = group_model._get_current_user_groups()
        _logger.debug("ARM: Found %s groups for user", len(groups))
        
        direct_menu_ids = set(groups.hidden_menu_line_ids.mapped('menu_id').ids)
        _logger.debug("ARM: Direct hidden menu IDs: %s", direct_menu_ids)
        
        if not direct_menu_ids:
            return set()

        all_hidden_ids = set(direct_menu_ids)
        pending_ids = set(direct_menu_ids)
        while pending_ids:
            child_ids = set(self.sudo().search([('parent_id', 'in', list(pending_ids))]).ids)
            child_ids -= all_hidden_ids
            if not child_ids:
                break
            all_hidden_ids.update(child_ids)
            pending_ids = child_ids
        
        _logger.debug("ARM: Total hidden menu IDs (including children): %s", all_hidden_ids)
        return all_hidden_ids

    @api.model
    @tools.ormcache('self.env.uid', 'debug')
    def _visible_menu_ids(self, debug=False):
        visible_menu_ids = super()._visible_menu_ids(debug=debug)
        hidden_menu_ids = self._arm_hidden_menu_ids()
        if not hidden_menu_ids:
            return visible_menu_ids

        visible_menu_ids = set(visible_menu_ids)
        visible_menu_ids.difference_update(hidden_menu_ids)
        return visible_menu_ids

    def _filter_visible_menus(self, *args, **kwargs):
        menus = super()._filter_visible_menus(*args, **kwargs)
        hidden_menu_ids = self._arm_hidden_menu_ids()
        if not hidden_menu_ids:
            return menus
        return menus.filtered(lambda menu: menu.id not in hidden_menu_ids)

    def load_menus(self, *args, **kwargs):
        _logger.debug("ARM: load_menus called for user %s", self.env.uid)
        result = super().load_menus(*args, **kwargs)
        hidden_menu_ids = self._arm_hidden_menu_ids()
        if not hidden_menu_ids or not isinstance(result, dict):
            return result

        # Filter the flat dictionary if it exists
        if 'menus' in result:
            _logger.debug("ARM: Filtering flat 'menus' dict")
            for menu_id in hidden_menu_ids:
                if str(menu_id) in result['menus']:
                    result['menus'].pop(str(menu_id))
                elif menu_id in result['menus']:
                    result['menus'].pop(menu_id)

        # Filter the tree structure
        def _filter_menu(node):
            if not isinstance(node, dict):
                return node
            
            node_id = node.get('id')
            if node_id in hidden_menu_ids:
                _logger.debug("ARM: Filtering out menu ID %s from tree", node_id)
                return None
                
            if 'children' in node:
                children = []
                for child in node.get('children', []):
                    filtered_child = _filter_menu(child)
                    if filtered_child:
                        children.append(filtered_child)
                node['children'] = children
            return node

        return _filter_menu(result) or {'children': []}
