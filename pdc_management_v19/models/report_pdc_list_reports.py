from odoo import _, api, fields, models


class PDCListReportWizard(models.TransientModel):
    """Shared wizard for the three snapshot list reports:
    Under Collection, Due Soon, and Bounced.

    The ``report_type`` field determines which dataset is fetched.
    """

    _name = 'pdc.list.report.wizard'
    _description = 'PDC List Report Wizard (Under Collection / Due Soon / Bounced)'

    report_type = fields.Selection(
        [
            ('under_collection', 'Under Collection'),
            ('due_soon', 'Due Soon'),
            ('bounced', 'Bounced'),
        ],
        string='Report Type',
        required=True,
        default='under_collection',
    )
    as_of_date = fields.Date(
        string='As of Date',
        required=True,
        default=fields.Date.today,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    check_type_filter = fields.Selection(
        [
            ('all', 'All Types'),
            ('received', 'Received'),
            ('issued', 'Issued'),
        ],
        string='Check Type',
        default='all',
        required=True,
    )
    partner_ids = fields.Many2many(
        'res.partner',
        string='Limit to Partners',
        help='Leave empty to include all partners.',
    )

    # ── Title helper ──────────────────────────────────────────────────────────
    @api.depends('report_type')
    def _compute_report_title(self):
        titles = {
            'under_collection': _('Checks Under Collection'),
            'due_soon': _('Checks Due Soon'),
            'bounced': _('Bounced Checks'),
        }
        for rec in self:
            rec.report_title = titles.get(rec.report_type, '')

    report_title = fields.Char(compute='_compute_report_title', store=False)

    # ── Data fetch ────────────────────────────────────────────────────────────
    def _get_checks(self):
        """Fetch checks according to ``report_type``."""
        company = self.company_id
        as_of = self.as_of_date

        domain = [('company_id', '=', company.id)]
        if self.check_type_filter != 'all':
            domain.append(('check_type', '=', self.check_type_filter))
        if self.partner_ids:
            domain.append(('partner_id', 'in', self.partner_ids.ids))

        if self.report_type == 'under_collection':
            domain.append(('state', '=', 'under_collection'))
            order = 'due_date, partner_id'

        elif self.report_type == 'due_soon':
            due_soon_days = company.pdc_due_soon_days or 7
            cutoff = fields.Date.add(as_of, days=due_soon_days)
            domain += [
                ('state', 'not in', ['cancelled', 'cleared', 'paid', 'returned', 'settled']),
                ('due_date', '>=', as_of),
                ('due_date', '<=', cutoff),
            ]
            order = 'due_date, partner_id'

        else:  # bounced
            domain.append(('state', '=', 'bounced'))
            order = 'bounce_date desc, partner_id'

        return self.env['pdc.check'].search(domain, order=order)

    # ── Actions ───────────────────────────────────────────────────────────────
    def action_print(self):
        self.ensure_one()
        ref_map = {
            'under_collection': 'pdc_management_v19.action_report_pdc_under_collection',
            'due_soon': 'pdc_management_v19.action_report_pdc_due_soon',
            'bounced': 'pdc_management_v19.action_report_pdc_bounced',
        }
        return (
            self.env.ref(ref_map[self.report_type])
            .report_action(self)
        )


# ── Abstract models (one per report — each has a distinct _name) ──────────────

class ReportPDCUnderCollection(models.AbstractModel):
    _name = 'report.pdc_management_v19.report_pdc_under_collection_document'
    _description = 'PDC Under Collection Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        wizard = self.env['pdc.list.report.wizard'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'pdc.list.report.wizard',
            'wizard': wizard,
            'checks': wizard._get_checks(),
            'report_title': _('Checks Under Collection'),
        }


class ReportPDCDueSoon(models.AbstractModel):
    _name = 'report.pdc_management_v19.report_pdc_due_soon_document'
    _description = 'PDC Due Soon Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        wizard = self.env['pdc.list.report.wizard'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'pdc.list.report.wizard',
            'wizard': wizard,
            'checks': wizard._get_checks(),
            'report_title': _('Checks Due Soon'),
        }


class ReportPDCBounced(models.AbstractModel):
    _name = 'report.pdc_management_v19.report_pdc_bounced_document'
    _description = 'PDC Bounced Checks Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        wizard = self.env['pdc.list.report.wizard'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'pdc.list.report.wizard',
            'wizard': wizard,
            'checks': wizard._get_checks(),
            'report_title': _('Bounced Checks'),
        }
