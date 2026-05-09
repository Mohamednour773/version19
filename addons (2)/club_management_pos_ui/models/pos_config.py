# -*- coding: utf-8 -*-
from odoo import fields, models


class PosConfig(models.Model):
    _inherit = 'pos.config'

    club_enable_pos_checkin = fields.Boolean(
        string='Enable POS Check-in / تفعيل تسجيل الحضور من POS',
        default=False,
        tracking=True,
        help='When enabled, a one-click attendance check-in button appears on the '
             'customer info card in POS. Disabled by default.\n'
             'عند التفعيل، يظهر زر تسجيل الحضور بنقرة واحدة على بطاقة معلومات العميل في نقطة البيع.',
    )
