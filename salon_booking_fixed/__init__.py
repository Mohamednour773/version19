# -*- coding: utf-8 -*-
from . import models
from . import controllers
from . import wizard


def post_init_hook(env):
    """
    Create res.groups and ir.rule records for Salon Booking.

    Handles the breaking change between:
      - Odoo 19 Enterprise: res.groups uses privilege_id (category_id removed)
      - Community: res.groups uses category_id
    """
    IrModelData = env['ir.model.data']
    Groups = env['res.groups']

    # Module category was created by the XML data file
    cat = env.ref('salon_booking.module_category_salon_booking', raise_if_not_found=False)
    if not cat:
        return

    use_privilege = 'privilege_id' in Groups._fields  # True on Enterprise 19+

    # ── Create privilege (Enterprise only) ──────────────────────────────────
    privilege = None
    if use_privilege:
        Privilege = env['res.groups.privilege']
        priv_data = IrModelData.search([
            ('module', '=', 'salon_booking'),
            ('name', '=', 'res_groups_privilege_salon_booking'),
        ], limit=1)
        if priv_data:
            privilege = Privilege.browse(priv_data.res_id)
        else:
            privilege = Privilege.create({
                'name': 'Salon Booking',
                'category_id': cat.id,
                'sequence': 80,
            })
            IrModelData.create({
                'module': 'salon_booking',
                'name': 'res_groups_privilege_salon_booking',
                'model': 'res.groups.privilege',
                'res_id': privilege.id,
                'noupdate': True,
            })

    # ── Helper: get-or-create a group ───────────────────────────────────────
    def _ensure_group(xml_name, display_name, implied_ids=None, user_ids=None):
        existing = IrModelData.search([
            ('module', '=', 'salon_booking'),
            ('name', '=', xml_name),
        ], limit=1)
        if existing:
            return Groups.browse(existing.res_id)

        vals = {'name': display_name}
        if use_privilege:
            vals['privilege_id'] = privilege.id
        else:
            vals['category_id'] = cat.id
        if implied_ids:
            vals['implied_ids'] = [(4, gid) for gid in implied_ids]
        if user_ids:
            vals['user_ids'] = [(4, uid) for uid in user_ids]

        group = Groups.create(vals)
        IrModelData.create({
            'module': 'salon_booking',
            'name': xml_name,
            'model': 'res.groups',
            'res_id': group.id,
            'noupdate': True,
        })
        return group

    base_user = env.ref('base.group_user')
    admin = env.ref('base.user_admin', raise_if_not_found=False)
    root = env.ref('base.user_root', raise_if_not_found=False)
    admin_ids = [u.id for u in [admin, root] if u]

    salon_user = _ensure_group(
        'group_salon_user', 'Salon User',
        implied_ids=[base_user.id],
    )
    salon_manager = _ensure_group(
        'group_salon_manager', 'Salon Manager',
        implied_ids=[salon_user.id],
        user_ids=admin_ids,
    )

    # ── ir.rule: calendar.event ─────────────────────────────────────────────
    IrRule = env['ir.rule']
    calendar_model = env.ref('calendar.model_calendar_event', raise_if_not_found=False)
    if not calendar_model:
        return

    def _ensure_rule(xml_name, name, group, domain, perms):
        existing = IrModelData.search([
            ('module', '=', 'salon_booking'),
            ('name', '=', xml_name),
        ], limit=1)
        if existing:
            return
        rule = IrRule.create({
            'name': name,
            'model_id': calendar_model.id,
            'groups': [(4, group.id)],
            'domain_force': domain,
            'perm_read': perms[0],
            'perm_write': perms[1],
            'perm_create': perms[2],
            'perm_unlink': perms[3],
        })
        IrModelData.create({
            'module': 'salon_booking',
            'name': xml_name,
            'model': 'ir.rule',
            'res_id': rule.id,
            'noupdate': True,
        })

    _ensure_rule(
        'rule_salon_appointment_user',
        'Salon User: read/write all salon appointments',
        salon_user,
        "[('appointment_type_id.is_salon_service', '=', True)]",
        (True, True, True, False),
    )
    _ensure_rule(
        'rule_salon_appointment_manager',
        'Salon Manager: full appointment access',
        salon_manager,
        "[(1, '=', 1)]",
        (True, True, True, True),
    )
