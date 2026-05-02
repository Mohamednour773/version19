from odoo import api, models


class ReportPDCCheckPrint(models.AbstractModel):
    """Abstract model that provides layout data for the check-print QWeb template.

    For each check document the report fetches the *default* ``pdc.bank.layout``
    for the check's bank (falling back to any active layout if no default is set).
    The layout coordinates are passed to the template so that each field can be
    positioned absolutely on the physical check paper.
    """

    _name = 'report.pdc_management_v19.report_pdc_check_document'
    _description = 'PDC Check Print Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        checks = self.env['pdc.check'].browse(docids)
        layout_map = {}
        for check in checks:
            layout = self.env['pdc.bank.layout']
            if check.bank_id:
                layout = self.env['pdc.bank.layout'].search(
                    [
                        ('bank_id', '=', check.bank_id.id),
                        ('is_default', '=', True),
                        ('active', '=', True),
                        ('company_id', '=', check.company_id.id),
                    ],
                    limit=1,
                )
                if not layout:
                    # Fall back to any active layout for this bank
                    layout = self.env['pdc.bank.layout'].search(
                        [
                            ('bank_id', '=', check.bank_id.id),
                            ('active', '=', True),
                        ],
                        limit=1,
                    )
            layout_map[check.id] = layout
        return {
            'doc_ids': docids,
            'doc_model': 'pdc.check',
            'docs': checks,
            'layout_map': layout_map,
        }
