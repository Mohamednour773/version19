import base64
import io
from datetime import date as date_type

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PDCAgingReportWizard(models.TransientModel):
    """Wizard that collects parameters for the PDC Aging Report.

    Supports both PDF (QWeb) and Excel (xlsxwriter) output.
    Aging buckets are configurable by the user.
    """

    _name = 'pdc.aging.report.wizard'
    _description = 'PDC Aging Report Wizard'

    # ── Parameters ────────────────────────────────────────────────────────────
    as_of_date = fields.Date(
        string='As of Date',
        required=True,
        default=fields.Date.today,
    )
    check_type = fields.Selection(
        [
            ('all', 'All Types'),
            ('received', 'Received'),
            ('issued', 'Issued'),
        ],
        string='Check Type',
        default='received',
        required=True,
    )
    state_filter = fields.Selection(
        [
            ('active', 'Active (exclude cleared/paid/settled/cancelled)'),
            ('overdue', 'Overdue Only'),
            ('all', 'All States'),
        ],
        string='Status Filter',
        default='active',
        required=True,
    )
    partner_ids = fields.Many2many(
        'res.partner',
        string='Limit to Partners',
        help='Leave empty to include all partners.',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency Filter',
        help='Leave empty for all currencies.',
    )

    # ── Aging bucket thresholds (days overdue) ────────────────────────────────
    bucket_1 = fields.Integer(string='Bucket 1 Up To (days)', default=30)
    bucket_2 = fields.Integer(string='Bucket 2 Up To (days)', default=60)
    bucket_3 = fields.Integer(string='Bucket 3 Up To (days)', default=90)
    bucket_4 = fields.Integer(string='Bucket 4 Up To (days)', default=120)

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _get_checks(self):
        """Return filtered ``pdc.check`` recordset based on wizard parameters."""
        domain = [('company_id', '=', self.company_id.id)]
        if self.check_type != 'all':
            domain.append(('check_type', '=', self.check_type))
        if self.partner_ids:
            domain.append(('partner_id', 'in', self.partner_ids.ids))
        if self.currency_id:
            domain.append(('currency_id', '=', self.currency_id.id))

        excluded = ['cancelled', 'settled', 'cleared', 'paid', 'returned']
        if self.state_filter == 'active':
            domain.append(('state', 'not in', excluded))
        elif self.state_filter == 'overdue':
            domain += [
                ('due_date', '<', self.as_of_date),
                ('state', 'not in', excluded),
            ]
        return self.env['pdc.check'].search(domain, order='partner_id, due_date')

    def _compute_aging_data(self):
        """Return list of per-partner-per-currency aging dicts for the template.

        Grouping is (partner_id, currency_id) so that mixed-currency partners
        never produce nonsense grand totals. Each dict represents one currency
        slice of one partner's exposure.
        """
        as_of = self.as_of_date
        b1, b2, b3, b4 = self.bucket_1, self.bucket_2, self.bucket_3, self.bucket_4
        checks = self._get_checks()

        # Key: (partner_id, currency_id)
        buckets = {}
        for check in checks:
            key = (check.partner_id.id, check.currency_id.id)
            if key not in buckets:
                buckets[key] = {
                    'partner': check.partner_id,
                    'currency': check.currency_id,
                    'checks': [],
                    'total': 0.0,
                    'current': 0.0,
                    'b1': 0.0,
                    'b2': 0.0,
                    'b3': 0.0,
                    'b4': 0.0,
                    'b5': 0.0,
                }
            days = (as_of - check.due_date).days if check.due_date else 0
            amt = check.amount
            b = buckets[key]
            b['checks'].append(check)
            b['total'] += amt
            if days <= 0:
                b['current'] += amt
            elif days <= b1:
                b['b1'] += amt
            elif days <= b2:
                b['b2'] += amt
            elif days <= b3:
                b['b3'] += amt
            elif days <= b4:
                b['b4'] += amt
            else:
                b['b5'] += amt

        # Sort: partner name, then currency name for deterministic output
        return sorted(
            buckets.values(),
            key=lambda d: (d['partner'].name or '', d['currency'].name or ''),
        )

    # ── Actions ───────────────────────────────────────────────────────────────
    def action_print_pdf(self):
        self.ensure_one()
        return (
            self.env.ref('pdc_management_v19.action_report_pdc_aging')
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
            'bold': True, 'font_size': 14, 'align': 'center', 'valign': 'vcenter',
        })
        subtitle_f = wb.add_format({'align': 'center', 'italic': True})
        header_f = wb.add_format({
            'bold': True, 'bg_color': '#1F4E79', 'font_color': 'white',
            'border': 1, 'align': 'center', 'valign': 'vcenter', 'text_wrap': True,
        })
        partner_f = wb.add_format({
            'bold': True, 'bg_color': '#D6E4F0', 'border': 1,
        })
        num_f = wb.add_format({'num_format': '#,##0.00', 'border': 1})
        partner_num_f = wb.add_format({
            'bold': True, 'num_format': '#,##0.00', 'bg_color': '#D6E4F0', 'border': 1,
        })
        grand_f = wb.add_format({
            'bold': True, 'bg_color': '#1F4E79', 'font_color': 'white',
            'num_format': '#,##0.00', 'border': 1,
        })
        grand_lbl_f = wb.add_format({
            'bold': True, 'bg_color': '#1F4E79', 'font_color': 'white', 'border': 1,
        })
        date_f = wb.add_format({'num_format': 'dd/mm/yyyy', 'border': 1})
        text_f = wb.add_format({'border': 1})

        ws = wb.add_worksheet('PDC Aging')
        ws.set_landscape()
        ws.fit_to_pages(1, 0)
        ws.set_zoom(80)

        b1, b2, b3, b4 = self.bucket_1, self.bucket_2, self.bucket_3, self.bucket_4
        ncols = 14
        # ── Title block ───────────────────────────────────────────────────────
        ws.merge_range(0, 0, 0, ncols - 1, 'PDC AGING REPORT', title_f)
        ws.merge_range(
            1, 0, 1, ncols - 1,
            f'As of {self.as_of_date} — {self.company_id.name}',
            subtitle_f,
        )
        ws.set_row(0, 24)
        ws.set_row(1, 18)

        # ── Column headers ────────────────────────────────────────────────────
        headers = [
            'Partner', 'Reference', 'Check No.', 'Bank', 'Branch',
            'Issue Date', 'Due Date', 'Currency', 'Amount',
            'Current', f'1–{b1}d', f'{b1+1}–{b2}d',
            f'{b2+1}–{b3}d', f'{b3+1}–{b4}d',  # NOTE: b5 header handled below
        ]
        # Replace last bucket header with ">b4 d"
        headers[-1] = f'>{b3}–{b4}d'
        headers.append(f'>{b4}d')
        headers = headers[:ncols]  # safety cap at 14

        ws.set_row(2, 30)
        for col, h in enumerate(headers):
            ws.write(2, col, h, header_f)

        # Column widths
        widths = [28, 15, 14, 22, 15, 12, 12, 10, 13, 13, 12, 12, 12, 12]
        for col, w in enumerate(widths):
            ws.set_column(col, col, w)

        # ── Data rows ─────────────────────────────────────────────────────────
        row = 3
        aging_data = self._compute_aging_data()
        as_of = self.as_of_date

        g_total = g_cur = g_b1 = g_b2 = g_b3 = g_b4 = g_b5 = 0.0

        for pd_data in aging_data:
            # Partner subtotal row
            ws.merge_range(row, 0, row, 7, pd_data['partner'].name, partner_f)
            ws.write(row, 8, pd_data['total'], partner_num_f)
            ws.write(row, 9, pd_data['current'], partner_num_f)
            ws.write(row, 10, pd_data['b1'], partner_num_f)
            ws.write(row, 11, pd_data['b2'], partner_num_f)
            ws.write(row, 12, pd_data['b3'], partner_num_f)
            ws.write(row, 13, pd_data['b4'], partner_num_f)
            row += 1

            for check in pd_data['checks']:
                days = (as_of - check.due_date).days if check.due_date else 0
                amt = check.amount
                ws.write(row, 0, '', text_f)
                ws.write(row, 1, check.name or '', text_f)
                ws.write(row, 2, check.check_number or '', text_f)
                ws.write(row, 3, check.bank_id.name if check.bank_id else '', text_f)
                ws.write(row, 4, check.branch or '', text_f)
                if check.issue_date:
                    ws.write_datetime(row, 5, check.issue_date, date_f)
                else:
                    ws.write(row, 5, '', text_f)
                if check.due_date:
                    ws.write_datetime(row, 6, check.due_date, date_f)
                else:
                    ws.write(row, 6, '', text_f)
                ws.write(row, 7, check.currency_id.name if check.currency_id else '', text_f)
                ws.write(row, 8, amt, num_f)

                zeros = [0.0] * 5
                if days <= 0:
                    zeros[0] = amt
                elif days <= b1:
                    zeros[1] = amt
                elif days <= b2:
                    zeros[2] = amt
                elif days <= b3:
                    zeros[3] = amt
                elif days <= b4:
                    zeros[4] = amt
                else:
                    zeros.append(amt)
                    zeros = zeros[1:]  # shift: drop 'current', add '>b4'

                for offset, val in enumerate(zeros[:5]):
                    ws.write(row, 9 + offset, val, num_f)
                row += 1

            g_total += pd_data['total']
            g_cur += pd_data['current']
            g_b1 += pd_data['b1']
            g_b2 += pd_data['b2']
            g_b3 += pd_data['b3']
            g_b4 += pd_data['b4']
            g_b5 += pd_data['b5']

        # Grand total row
        ws.merge_range(row, 0, row, 7, 'GRAND TOTAL', grand_lbl_f)
        for col, val in enumerate(
            [g_total, g_cur, g_b1, g_b2, g_b3, g_b4, g_b5], 8
        ):
            ws.write(row, col, val, grand_f)

        wb.close()
        xlsx_data = output.getvalue()

        attach = self.env['ir.attachment'].create({
            'name': f'PDC_Aging_{self.as_of_date}.xlsx',
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


class ReportPDCAging(models.AbstractModel):
    """Abstract model that feeds data to the PDF QWeb aging template."""

    _name = 'report.pdc_management_v19.report_pdc_aging_document'
    _description = 'PDC Aging Report (PDF data provider)'

    @api.model
    def _get_report_values(self, docids, data=None):
        wizards = self.env['pdc.aging.report.wizard'].browse(docids)
        wizard = wizards[0] if wizards else wizards
        aging_data = wizard._compute_aging_data()
        b1, b2, b3, b4 = wizard.bucket_1, wizard.bucket_2, wizard.bucket_3, wizard.bucket_4
        return {
            'doc_ids': docids,
            'doc_model': 'pdc.aging.report.wizard',
            'wizard': wizard,
            'aging_data': aging_data,
            'bucket_labels': [
                'Current',
                f'1–{b1}d',
                f'{b1+1}–{b2}d',
                f'{b2+1}–{b3}d',
                f'{b3+1}–{b4}d',
                f'>{b4}d',
            ],
        }
