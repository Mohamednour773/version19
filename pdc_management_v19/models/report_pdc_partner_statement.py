import base64
import io

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PDCPartnerStatementWizard(models.TransientModel):
    """Wizard for the PDC Partner Statement report.

    Shows all check transactions for one or more partners within a date range,
    grouped by partner with running subtotals per state.
    """

    _name = 'pdc.partner.statement.wizard'
    _description = 'PDC Partner Statement Wizard'

    # ── Parameters ────────────────────────────────────────────────────────────
    date_from = fields.Date(
        string='From Date',
        required=True,
        default=lambda self: fields.Date.today().replace(month=1, day=1),
    )
    date_to = fields.Date(
        string='To Date',
        required=True,
        default=fields.Date.today,
    )
    partner_ids = fields.Many2many(
        'res.partner',
        string='Partners',
        required=True,
        help='Select one or more partners to include in the statement.',
    )
    check_type = fields.Selection(
        [
            ('all', 'All Types'),
            ('received', 'Received'),
            ('issued', 'Issued'),
        ],
        string='Check Type',
        default='all',
        required=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    include_cancelled = fields.Boolean(
        string='Include Cancelled',
        default=False,
    )
    group_by_partner = fields.Boolean(
        string='Group by Partner',
        default=True,
    )

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _get_statement_lines(self):
        """Return per-partner statement data list."""
        if not self.partner_ids:
            raise UserError(_('Please select at least one partner.'))

        domain = [
            ('company_id', '=', self.company_id.id),
            ('partner_id', 'in', self.partner_ids.ids),
            ('issue_date', '>=', self.date_from),
            ('issue_date', '<=', self.date_to),
        ]
        if self.check_type != 'all':
            domain.append(('check_type', '=', self.check_type))
        if not self.include_cancelled:
            domain.append(('state', '!=', 'cancelled'))

        checks = self.env['pdc.check'].search(
            domain, order='partner_id, issue_date, due_date'
        )

        partners = {}
        for check in checks:
            pid = check.partner_id.id
            if pid not in partners:
                partners[pid] = {
                    'partner': check.partner_id,
                    'checks': [],
                    'total': 0.0,
                    'by_state': {},
                    'currency': check.currency_id,
                }
            partners[pid]['checks'].append(check)
            partners[pid]['total'] += check.amount
            state = check.state
            partners[pid]['by_state'][state] = (
                partners[pid]['by_state'].get(state, 0.0) + check.amount
            )

        return list(partners.values())

    # ── Actions ───────────────────────────────────────────────────────────────
    def action_print_pdf(self):
        self.ensure_one()
        return (
            self.env.ref('pdc_management_v19.action_report_pdc_partner_statement')
            .report_action(self)
        )

    def action_print_excel(self):
        self.ensure_one()
        try:
            import xlsxwriter  # noqa: F401
        except ImportError:
            raise UserError(
                _('xlsxwriter is not installed. Please run: pip install xlsxwriter')
            )

        output = io.BytesIO()
        wb = xlsxwriter.Workbook(output, {'in_memory': True})

        # ── Formats ───────────────────────────────────────────────────────────
        title_f = wb.add_format({
            'bold': True, 'font_size': 14, 'align': 'center',
        })
        subtitle_f = wb.add_format({'align': 'center', 'italic': True})
        header_f = wb.add_format({
            'bold': True, 'bg_color': '#1F4E79', 'font_color': 'white',
            'border': 1, 'align': 'center', 'text_wrap': True,
        })
        partner_f = wb.add_format({
            'bold': True, 'bg_color': '#D6E4F0', 'border': 1, 'font_size': 12,
        })
        num_f = wb.add_format({'num_format': '#,##0.00', 'border': 1})
        subtotal_f = wb.add_format({
            'bold': True, 'num_format': '#,##0.00',
            'bg_color': '#EBF5FB', 'border': 1,
        })
        date_f = wb.add_format({'num_format': 'dd/mm/yyyy', 'border': 1})
        text_f = wb.add_format({'border': 1})
        state_f = wb.add_format({'border': 1, 'align': 'center'})

        ws = wb.add_worksheet('Partner Statement')
        ws.set_landscape()
        ws.fit_to_pages(1, 0)

        # Title
        ncols = 10
        ws.merge_range(
            0, 0, 0, ncols - 1,
            f'PDC PARTNER STATEMENT — {self.company_id.name}',
            title_f,
        )
        ws.merge_range(
            1, 0, 1, ncols - 1,
            f'Period: {self.date_from} to {self.date_to}',
            subtitle_f,
        )
        ws.set_row(0, 24)
        ws.set_row(1, 18)

        headers = [
            'Reference', 'Check No.', 'Bank', 'Branch',
            'Issue Date', 'Due Date', 'Type', 'Status', 'Currency', 'Amount',
        ]
        ws.set_row(2, 28)
        for col, h in enumerate(headers):
            ws.write(2, col, h, header_f)

        widths = [15, 14, 22, 15, 12, 12, 12, 18, 10, 14]
        for col, w in enumerate(widths):
            ws.set_column(col, col, w)

        row = 3
        statement_data = self._get_statement_lines()

        for pd_data in statement_data:
            # Partner header row
            ws.merge_range(
                row, 0, row, ncols - 1,
                pd_data['partner'].name,
                partner_f,
            )
            row += 1

            for check in pd_data['checks']:
                ws.write(row, 0, check.name or '', text_f)
                ws.write(row, 1, check.check_number or '', text_f)
                ws.write(row, 2, check.bank_id.name if check.bank_id else '', text_f)
                ws.write(row, 3, check.branch or '', text_f)
                if check.issue_date:
                    ws.write_datetime(row, 4, check.issue_date, date_f)
                else:
                    ws.write(row, 4, '', text_f)
                if check.due_date:
                    ws.write_datetime(row, 5, check.due_date, date_f)
                else:
                    ws.write(row, 5, '', text_f)
                ws.write(row, 6, dict(check._fields['check_type'].selection).get(
                    check.check_type, check.check_type), text_f)
                ws.write(row, 7, dict(check._fields['state'].selection).get(
                    check.state, check.state), state_f)
                ws.write(row, 8, check.currency_id.name if check.currency_id else '', text_f)
                ws.write(row, 9, check.amount, num_f)
                row += 1

            # Partner subtotal row
            ws.merge_range(
                row, 0, row, 8,
                f'Subtotal — {pd_data["partner"].name}',
                subtotal_f,
            )
            ws.write(row, 9, pd_data['total'], subtotal_f)
            row += 1
            row += 1  # blank separator

        wb.close()
        xlsx_data = output.getvalue()

        attach = self.env['ir.attachment'].create({
            'name': f'PDC_Statement_{self.date_from}_{self.date_to}.xlsx',
            'type': 'binary',
            'datas': base64.b64encode(xlsx_data).decode(),
            'mimetype': (
                'application/vnd.openxmlformats-officedocument'
                '.spreadsheetml.sheet'
            ),
            'res_model': self._name,
            'res_id': self.id,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attach.id}?download=true',
            'target': 'self',
        }


class ReportPDCPartnerStatement(models.AbstractModel):
    """Abstract model that feeds data to the PDF partner-statement QWeb template."""

    _name = 'report.pdc_management_v19.report_pdc_partner_statement_document'
    _description = 'PDC Partner Statement (PDF data provider)'

    @api.model
    def _get_report_values(self, docids, data=None):
        wizards = self.env['pdc.partner.statement.wizard'].browse(docids)
        wizard = wizards[0] if wizards else wizards
        statement_data = wizard._get_statement_lines()
        return {
            'doc_ids': docids,
            'doc_model': 'pdc.partner.statement.wizard',
            'wizard': wizard,
            'statement_data': statement_data,
        }
