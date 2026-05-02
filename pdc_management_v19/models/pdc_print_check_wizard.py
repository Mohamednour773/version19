from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PDCPrintCheckWizard(models.TransientModel):
    """Wizard: print one or more issued checks.

    Lets the user choose a specific print layout (or use each bank's default),
    optionally marks the check(s) as Printed after generating the PDF.
    Works for single and batch printing.
    """
    _name = 'pdc.print.check.wizard'
    _description = 'Print PDC Check'

    check_ids = fields.Many2many(
        'pdc.check', string='Checks',
        domain=[
            ('check_type', 'in', ['issued', 'guarantee_issued']),
            ('state', '=', 'registered'),
        ],
        required=True,
    )
    layout_id = fields.Many2one(
        'pdc.bank.layout', string='Print Layout',
        help='Select a layout to use for all checks in this batch.\n'
             'Leave blank to use the default layout for each check\'s bank.\n'
             'When printing checks from multiple banks, each will use its own default.',
    )
    mark_as_printed = fields.Boolean(
        string='Mark Checks as Printed After Generating PDF',
        default=True,
        help='Advances check state from Registered → Printed and logs the operation.\n'
             'Uncheck if you need to re-print a test page without recording the state change.',
    )
    check_count = fields.Integer(compute='_compute_summary', store=False)
    bank_count = fields.Integer(compute='_compute_summary', store=False)
    multi_bank = fields.Boolean(compute='_compute_summary', store=False)

    @api.depends('check_ids')
    def _compute_summary(self):
        for wiz in self:
            wiz.check_count = len(wiz.check_ids)
            banks = wiz.check_ids.mapped('bank_id')
            wiz.bank_count = len(banks)
            wiz.multi_bank = len(banks) > 1

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_ids = self._context.get('active_ids') or []
        active_model = self._context.get('active_model')
        if active_model == 'pdc.check' and active_ids and 'check_ids' in fields_list:
            res['check_ids'] = [(6, 0, active_ids)]
            # Pre-fill with the default layout of the first check's bank
            if 'layout_id' in fields_list:
                checks = self.env['pdc.check'].browse(active_ids)
                if checks:
                    layout = self.env['pdc.bank.layout'].search(
                        [
                            ('bank_id', '=', checks[0].bank_id.id),
                            ('is_default', '=', True),
                            ('active', '=', True),
                        ],
                        limit=1,
                    )
                    if layout:
                        res['layout_id'] = layout.id
        return res

    # ── Action ────────────────────────────────────────────────────────────────

    def action_print(self):
        """Mark checks as printed (if requested), then return the PDF report action."""
        self.ensure_one()
        if not self.check_ids:
            raise UserError(_('Please select at least one check to print.'))

        if self.mark_as_printed:
            errors = []
            for check in self.check_ids:
                try:
                    check.action_print_check()
                except Exception as exc:
                    errors.append(
                        _('• %(name)s: %(err)s', name=check.name, err=str(exc))
                    )
            if errors:
                raise UserError(_(
                    'Some checks could not be marked as printed:\n%(errors)s',
                    errors='\n'.join(errors),
                ))

        report = self.env.ref('pdc_management_v19.action_report_pdc_check')
        return report.report_action(self.check_ids)


# ── pdc.check extension ───────────────────────────────────────────────────────

class PDCCheckPrintAction(models.Model):
    """Adds action_open_print_check_wizard() to pdc.check."""
    _inherit = 'pdc.check'

    def action_open_print_check_wizard(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Print Check'),
            'res_model': 'pdc.print.check.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_check_ids': [(6, 0, self.ids)],
                'active_ids': self.ids,
                'active_model': 'pdc.check',
            },
        }
