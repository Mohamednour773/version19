# -*- coding: utf-8 -*-
import logging
from odoo import models, fields

_logger = logging.getLogger(__name__)


class ClubMembership(models.Model):
    """Phase 2 extension: adds a flag that is set when a registration-fee
    payment is received through POS for this membership.

    The original module tracks registration fee eligibility by searching for a
    separate ``is_registration_fee`` membership record.  This flag gives
    reception an additional at-a-glance indicator without altering the existing
    lookup logic in ``action_confirm``.
    """
    _inherit = 'club.membership'

    registration_fee_paid = fields.Boolean(
        string='Registration Fee Paid (POS)',
        default=False,
        tracking=True,
        help=(
            'Automatically set when a registration-fee package is sold via POS '
            'and linked to this membership.  Does not replace the dedicated '
            'registration-fee membership record required by action_confirm.'
        ),
    )
