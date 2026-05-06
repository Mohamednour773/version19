# -*- coding: utf-8 -*-
import logging
from odoo import models, fields

_logger = logging.getLogger(__name__)


class PosConfig(models.Model):
    _inherit = 'pos.config'

    club_branch_id = fields.Many2one(
        'club.branch',
        string='Club Branch',
        help=(
            'When set, only packages from this branch will be available in this '
            'POS session. Leave empty to show packages from all branches the user '
            'has access to.'
        ),
    )
