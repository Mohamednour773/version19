# -*- coding: utf-8 -*-
import base64
import io
import json
import logging
import re
import urllib.request
import urllib.error

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# ── Odoo 19 Chart of Accounts Import Columns ──────────────────────
# These are the exact column names Odoo expects when importing accounts
COA_COLUMNS = [
    'code', 'name', 'account_type', 'reconcile',
    'deprecated', 'group_id/complete_name', 'note'
]

# account_type valid values in Odoo 19
ACCOUNT_TYPES = [
    'asset_receivable', 'asset_cash', 'asset_current', 'asset_non_current',
    'asset_prepayments', 'asset_fixed', 'liability_payable',
    'liability_credit_card', 'liability_current', 'liability_non_current',
    'equity', 'equity_unaffected', 'income', 'income_other',
    'expense', 'expense_depreciation', 'expense_direct_cost', 'off_balance'
]

# Opening Entries Import Columns
OE_COLUMNS = [
    'date', 'ref', 'journal_id/name',
    'line_ids/account_id/code', 'line_ids/name',
    'line_ids/debit', 'line_ids/credit'
]

# Phase 1: Chart of Accounts only
EXCEL_COA_SYSTEM_PROMPT = """
You are a Senior Odoo Accounting Consultant.
Analyze the input data and generate ONLY the Chart of Accounts structure.

ODOO 19 ACCOUNT TYPES (use EXACTLY one of these):
asset_receivable, asset_cash, asset_current, asset_non_current,
asset_prepayments, asset_fixed, liability_payable, liability_credit_card,
liability_current, liability_non_current, equity, equity_unaffected,
income, income_other, expense, expense_depreciation, expense_direct_cost, off_balance

RULES:
1. Account codes = numeric strings only ("1010", "110100")
2. Group/header accounts: deprecated=true, no transactions
3. Transaction accounts: deprecated=false
4. reconcile=true ONLY for receivable/payable accounts
5. group_id/complete_name format: "Assets" or "Assets / Current Assets"
6. Keep names SHORT (max 60 chars)
7. Generate ALL accounts found in the input

Return ONLY raw JSON. No markdown. No text before or after. Start with { end with }.

{
  "analysis_summary": "brief description",
  "company_name": "name or empty",
  "warnings": [],
  "chart_of_accounts": [
    {
      "code": "1000",
      "name": "Current Assets",
      "account_type": "asset_current",
      "reconcile": false,
      "deprecated": true,
      "group_id/complete_name": "Assets",
      "note": ""
    }
  ]
}
"""

# Phase 2: Opening Entries only
EXCEL_OE_SYSTEM_PROMPT = """
You are a Senior Odoo Accounting Consultant.
Given a trial balance, generate ONLY the Opening Journal Entries for Odoo import.

RULES:
1. One line per account that has a non-zero balance
2. Debit balance accounts: put amount in debit column, 0 in credit
3. Credit balance accounts: put amount in credit column, 0 in debit
4. Total debit MUST equal total credit - add a rounding/difference line if needed
5. date = fiscal year start date provided
6. ref = "OE/YYYY/001"
7. journal_id/name = "Opening Entries"
8. All amounts POSITIVE numbers
9. Skip accounts with zero balance

Return ONLY raw JSON. No markdown. Start with { end with }.

{
  "total_debit": 0.0,
  "total_credit": 0.0,
  "is_balanced": true,
  "warnings": [],
  "opening_entries": [
    {
      "date": "2024-01-01",
      "ref": "OE/2024/001",
      "journal_id/name": "Opening Entries",
      "line_ids/account_id/code": "1100",
      "line_ids/name": "Opening Balance",
      "line_ids/debit": 50000.0,
      "line_ids/credit": 0.0
    }
  ]
}
"""

EXCEL_AI_SYSTEM_PROMPT = EXCEL_COA_SYSTEM_PROMPT  # backward compat


class SmartExcelGenerator(models.Model):
    _name = 'smart.excel.generator'
    _description = 'Smart Excel Generator — Chart of Accounts & Opening Entries'
    _order = 'create_date desc'
    _inherit = ['mail.thread']

    name = fields.Char('Title', required=True, tracking=True)
    task_id = fields.Many2one('smart.task', 'Related Task', tracking=True)
    client_id = fields.Many2one('res.partner', 'Client', tracking=True)

    input_type = fields.Selection([
        ('trial_balance', 'Trial Balance (ميزان مراجعة)'),
        ('account_list', 'Account List (قائمة حسابات)'),
    ], string='Input Type', required=True, default='trial_balance')

    odoo_version = fields.Selection([
        ('Odoo 19', 'Odoo 19'), ('Odoo 18', 'Odoo 18'),
        ('Odoo 17', 'Odoo 17'), ('Odoo 16', 'Odoo 16'),
    ], string='Target Odoo Version', default='Odoo 19', required=True)

    fiscal_year_start = fields.Date('Fiscal Year Start')

    # Input file
    input_file = fields.Binary('Input File (Excel/CSV)', attachment=True)
    input_filename = fields.Char('Input Filename')

    # Raw text input (alternative to file)
    input_text = fields.Text(
        'Or Paste Account Data',
        help='Paste tab-separated or CSV data if you do not have an Excel file'
    )

    # Status
    state = fields.Selection([
        ('draft', 'Draft'),
        ('processing', 'Processing...'),
        ('done', 'Done'),
        ('error', 'Error'),
    ], default='draft', tracking=True)

    ai_analysis = fields.Html('AI Analysis')
    error_message = fields.Text('Error Details')

    # Output files
    coa_file = fields.Binary('Chart of Accounts (Excel)', attachment=True, readonly=True)
    coa_filename = fields.Char('COA Filename', readonly=True)
    coa_count = fields.Integer('Accounts Generated', readonly=True)

    oe_file = fields.Binary('Opening Entries (Excel)', attachment=True, readonly=True)
    oe_filename = fields.Char('OE Filename', readonly=True)
    oe_count = fields.Integer('Journal Lines Generated', readonly=True)

    is_balanced = fields.Boolean('Entries Balanced', readonly=True)
    total_debit = fields.Float('Total Debit', readonly=True)
    total_credit = fields.Float('Total Credit', readonly=True)

    # ── Main Action ───────────────────────────────────────────────
    def action_generate(self):
        self.ensure_one()
        if not self.input_file and not self.input_text:
            raise UserError(_('Please upload a file or paste account data first.'))

        self.write({'state': 'processing', 'error_message': False})

        try:
            # Step 1: Read input data
            input_data = self._read_input()

            # Step 2a: Phase 1 — Chart of Accounts
            self.message_post(body=_('<b>Phase 1: Generating Chart of Accounts...</b>'), message_type='notification')
            coa_result = self._call_ai_phase(input_data, 'coa')

            # Step 2b: Phase 2 — Opening Entries (only for trial balance)
            oe_result = {'opening_entries': [], 'total_debit': 0, 'total_credit': 0, 'is_balanced': True, 'warnings': []}
            if self.input_type == 'trial_balance':
                self.message_post(body=_('<b>Phase 2: Generating Opening Entries...</b>'), message_type='notification')
                oe_result = self._call_ai_phase(input_data, 'oe')

            # Merge results
            ai_result = {
                'analysis_summary': coa_result.get('analysis_summary', ''),
                'company_name': coa_result.get('company_name', ''),
                'fiscal_year_start': str(self.fiscal_year_start or fields.Date.today()),
                'warnings': coa_result.get('warnings', []) + oe_result.get('warnings', []),
                'chart_of_accounts': coa_result.get('chart_of_accounts', []),
                'opening_entries': oe_result.get('opening_entries', []),
                'total_debit': oe_result.get('total_debit', 0),
                'total_credit': oe_result.get('total_credit', 0),
                'is_balanced': oe_result.get('is_balanced', True),
            }

            # Step 3: Generate Excel files
            self._generate_excel_files(ai_result)

            # Step 4: Show analysis
            self._update_analysis_html(ai_result)

            self.state = 'done'
            self.message_post(
                body=_('<b>Excel files generated successfully!</b><br/>'
                       'Chart of Accounts: %s accounts<br/>'
                       'Opening Entries: %s lines<br/>'
                       'Balanced: %s') % (
                    self.coa_count, self.oe_count,
                    'Yes ✅' if self.is_balanced else 'No ⚠️'
                ),
                message_type='notification'
            )

        except Exception as e:
            _logger.exception("Excel generation failed for %s", self.id)
            self.write({
                'state': 'error',
                'error_message': str(e),
            })
            raise UserError(_('Generation failed: %s') % str(e))

    def action_reset(self):
        self.write({
            'state': 'draft',
            'coa_file': False, 'coa_filename': False, 'coa_count': 0,
            'oe_file': False, 'oe_filename': False, 'oe_count': 0,
            'ai_analysis': False, 'error_message': False,
            'is_balanced': False, 'total_debit': 0, 'total_credit': 0,
        })

    # ── Input Reader ──────────────────────────────────────────────
    def _read_input(self):
        """Read input file or text and return as string."""
        if self.input_file:
            file_data = base64.b64decode(self.input_file)
            filename = (self.input_filename or '').lower()

            if filename.endswith('.csv'):
                # Try UTF-8, then common Arabic encodings
                for enc in ('utf-8', 'utf-8-sig', 'cp1256', 'iso-8859-6', 'latin-1'):
                    try:
                        return file_data.decode(enc)
                    except UnicodeDecodeError:
                        continue
                return file_data.decode('utf-8', errors='replace')

            elif filename.endswith(('.xlsx', '.xls')):
                last_error = None

                # 1. Try zipfile raw reader (no dependencies, works always for .xlsx)
                if filename.endswith('.xlsx'):
                    try:
                        return self._read_xlsx_raw(file_data)
                    except Exception as e:
                        last_error = str(e)
                        _logger.error("Raw xlsx read failed: %s", e)
                        raise UserError(_('Raw xlsx read error: %s') % str(e))

                # 2. Try openpyxl
                try:
                    from openpyxl import load_workbook
                    wb = load_workbook(io.BytesIO(file_data), read_only=True, data_only=True)
                    ws = wb.active
                    rows = []
                    for row in ws.iter_rows(values_only=True):
                        str_row = [str(cell) if cell is not None else '' for cell in row]
                        encoded = []
                        for v in str_row:
                            if ',' in v or '"' in v or '\n' in v:
                                v = '"' + v.replace('"', '""') + '"'
                            encoded.append(v)
                        rows.append(','.join(encoded))
                    wb.close()
                    return '\n'.join(rows)
                except ImportError:
                    pass
                except Exception as e:
                    last_error = str(e)
                    _logger.warning("openpyxl read failed: %s", e)

                # 3. Try xlrd
                try:
                    import xlrd
                    wb = xlrd.open_workbook(file_contents=file_data)
                    ws = wb.sheet_by_index(0)
                    rows = []
                    for row_idx in range(ws.nrows):
                        str_row = []
                        for col in range(ws.ncols):
                            v = ws.cell_value(row_idx, col)
                            str_row.append(str(v) if v is not None else '')
                        encoded = []
                        for v in str_row:
                            if ',' in v or '"' in v or '\n' in v:
                                v = '"' + v.replace('"', '""') + '"'
                            encoded.append(v)
                        rows.append(','.join(encoded))
                    return '\n'.join(rows)
                except ImportError:
                    pass
                except Exception as e:
                    last_error = str(e)
                    _logger.warning("xlrd read failed: %s", e)

                # Nothing worked
                raise UserError(_(
                    'Cannot read this Excel file automatically.\n'
                    'Solution: Open the file in Excel > Select All (Ctrl+A) > '
                    'Copy (Ctrl+C) > Paste in the text field below.'
                ))
            else:
                # Try as text
                # Try UTF-8, then common Arabic encodings
                for enc in ('utf-8', 'utf-8-sig', 'cp1256', 'iso-8859-6', 'latin-1'):
                    try:
                        return file_data.decode(enc)
                    except UnicodeDecodeError:
                        continue
                return file_data.decode('utf-8', errors='replace')

        elif self.input_text:
            return self.input_text

        raise UserError(_('No input data provided.'))

    def _read_xlsx_raw(self, file_data):
        """Read xlsx without external libraries using zipfile + xml parsing."""
        import zipfile
        import xml.etree.ElementTree as ET

        zf = zipfile.ZipFile(io.BytesIO(file_data))

        # Read shared strings
        shared_strings = []
        try:
            sst_raw = zf.read('xl/sharedStrings.xml')
            # Detect encoding from XML declaration or default to utf-8
            sst_xml = sst_raw
            sst_root = ET.fromstring(sst_xml)
            ns = {'ns': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            for si in sst_root.findall('.//ns:si', ns):
                # Get all text within <t> tags
                texts = [t.text or '' for t in si.findall('.//ns:t', ns)]
                shared_strings.append(''.join(texts))
        except KeyError:
            pass  # No shared strings

        # Read first sheet
        sheet_files = [n for n in zf.namelist() if n.startswith('xl/worksheets/sheet') and n.endswith('.xml')]
        if not sheet_files:
            raise ValueError("No sheets found in xlsx")

        sheet_xml = zf.read(sorted(sheet_files)[0])
        sheet_root = ET.fromstring(sheet_xml)
        ns = {'ns': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}

        rows = []
        for row_el in sheet_root.findall('.//ns:row', ns):
            cells = []
            for cell_el in row_el.findall('ns:c', ns):
                cell_type = cell_el.get('t', '')
                val_el = cell_el.find('ns:v', ns)
                val = ''
                if val_el is not None and val_el.text is not None:
                    if cell_type == 's':
                        # Shared string
                        try:
                            val = shared_strings[int(val_el.text)]
                        except (IndexError, ValueError):
                            val = val_el.text
                    elif cell_type == 'b':
                        val = 'TRUE' if val_el.text == '1' else 'FALSE'
                    else:
                        # Number or date
                        val = val_el.text
                cells.append(val)
            if any(cells):  # Skip empty rows
                # CSV-encode
                encoded = []
                for v in cells:
                    v = str(v) if v else ''
                    if ',' in v or '"' in v or '\n' in v:
                        v = '"' + v.replace('"', '""') + '"'
                    encoded.append(v)
                rows.append(','.join(encoded))

        zf.close()
        if not rows:
            raise ValueError("No data found in xlsx")
        return '\n'.join(rows)

        # ── AI Call ───────────────────────────────────────────────────
    def _call_ai_phase(self, input_data, phase):
        """Call AI for a specific phase: coa or oe."""
        if phase == 'coa':
            system = EXCEL_COA_SYSTEM_PROMPT
        else:
            system = EXCEL_OE_SYSTEM_PROMPT

        fiscal_hint = f'Fiscal year start: {self.fiscal_year_start}' if self.fiscal_year_start else ''
        user_prompt = (
            f"Input Type: {dict(self._fields['input_type'].selection).get(self.input_type)}\n"
            f"Target Odoo Version: {self.odoo_version}\n"
            f"Client: {self.client_id.name if self.client_id else 'Unknown'}\n"
            f"{fiscal_hint}\n\n"
            f"INPUT DATA:\n{input_data[:5000]}"
        )
        return self._call_openai(system, user_prompt, max_tokens=4000)

    def _call_openai(self, system_prompt, user_prompt, max_tokens=4000):
        """Call OpenAI and return parsed JSON."""
        api_key = self.env['ir.config_parameter'].sudo().get_param('smart_task_hub_test.openai_api_key', '')
        if not api_key:
            raise UserError(_('OpenAI API key not configured.'))
        model = self.env['ir.config_parameter'].sudo().get_param('smart_task_hub_test.openai_model', 'o4-mini')
        is_reasoning = model.startswith('o3') or model.startswith('o4') or model.startswith('o1')

        full_system = (system_prompt +
            "\n\nCRITICAL: RAW JSON ONLY. No markdown. Start { end }. No trailing commas. Double quotes only.")

        if is_reasoning:
            payload_dict = {
                'model': model,
                'messages': [{'role': 'user', 'content': full_system + '\n\n' + user_prompt}],
                'max_completion_tokens': max_tokens * 2,
            }
        else:
            payload_dict = {
                'model': model,
                'messages': [
                    {'role': 'system', 'content': full_system},
                    {'role': 'user', 'content': user_prompt},
                ],
                'temperature': 0.1,
                'max_tokens': max_tokens,
            }

        payload = json.dumps(payload_dict).encode('utf-8')
        req_obj = urllib.request.Request(
            'https://api.openai.com/v1/chat/completions',
            data=payload,
            headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
            method='POST'
        )
        try:
            with urllib.request.urlopen(req_obj, timeout=180) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                raw = data['choices'][0]['message']['content'] or ''
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8')
            raise UserError(_('OpenAI API error %s: %s') % (e.code, body[:300]))

        cleaned = raw.strip()
        if '```' in cleaned:
            cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned, flags=re.MULTILINE)
            cleaned = re.sub(r'```\s*$', '', cleaned, flags=re.MULTILINE).strip()

        match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if not match:
            raise UserError(_('AI did not return valid JSON: %s') % raw[:200])

        json_str = match.group()
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            json_str = re.sub(r',\s*([}\]])', r'\1', json_str)
            json_str = re.sub(r'[\x00-\x08\x0b-\x1f\x7f]', ' ', json_str)
            try:
                return json.loads(json_str)
            except json.JSONDecodeError as e:
                _logger.error("JSON parse failed: %s", e)
                return {
                    'analysis_summary': f'Parse warning: {e}',
                    'warnings': [str(e)],
                    'chart_of_accounts': [], 'opening_entries': [],
                    'total_debit': 0, 'total_credit': 0, 'is_balanced': True,
                }


    def _call_ai(self, input_data):
        """Call GPT to analyze input and generate COA + OE structure."""
        api_key = self.env['ir.config_parameter'].sudo().get_param(
            'smart_task_hub_test.openai_api_key', '')
        if not api_key:
            raise UserError(_('OpenAI API key not configured in Smart Task Hub Settings.'))

        model = self.env['ir.config_parameter'].sudo().get_param(
            'smart_task_hub_test.openai_model', 'o4-mini')

        fiscal_hint = ''
        if self.fiscal_year_start:
            fiscal_hint = f'\nFiscal year start: {self.fiscal_year_start}'

        user_prompt = (
            f"Input Type: {dict(self._fields['input_type'].selection).get(self.input_type)}\n"
            f"Target Odoo Version: {self.odoo_version}\n"
            f"Client: {self.client_id.name if self.client_id else 'Unknown'}"
            f"{fiscal_hint}\n\n"
            f"INPUT DATA:\n{input_data[:6000]}"
        )

        full_system = EXCEL_AI_SYSTEM_PROMPT + \
            "\n\nCRITICAL JSON RULES:\n1. Return RAW JSON ONLY — no markdown, no text before or after\n2. Start with { and end with }\n3. NO trailing commas (last item in array/object must NOT have comma)\n4. ALL strings must use double quotes\n5. NO newlines inside string values — use space instead\n6. Keep string values SHORT — max 200 chars per value"

        is_reasoning = model.startswith('o3') or model.startswith('o4') or model.startswith('o1')

        # Limit input data to avoid huge outputs
        input_data_trimmed = input_data[:4000]

        if is_reasoning:
            payload = json.dumps({
                'model': model,
                'messages': [
                    {'role': 'user', 'content': full_system + '\n\n' + user_prompt.replace(input_data, input_data_trimmed)}
                ],
                'max_completion_tokens': 8000,
            }).encode('utf-8')
        else:
            payload = json.dumps({
                'model': model,
                'messages': [
                    {'role': 'system', 'content': full_system},
                    {'role': 'user', 'content': user_prompt.replace(input_data, input_data_trimmed)},
                ],
                'temperature': 0.1,
                'max_tokens': 8000,
            }).encode('utf-8')

        req = urllib.request.Request(
            'https://api.openai.com/v1/chat/completions',
            data=payload,
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            method='POST'
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                raw = data['choices'][0]['message']['content'] or ''
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8')
            raise UserError(_('OpenAI API error %s: %s') % (e.code, body[:300]))

        # Parse JSON — robust parser
        cleaned = raw.strip()
        # Strip markdown code blocks
        if '```' in cleaned:
            cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned, flags=re.MULTILINE)
            cleaned = re.sub(r'```\s*$', '', cleaned, flags=re.MULTILINE).strip()

        # Find JSON object
        match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if not match:
            raise UserError(_('AI did not return valid JSON. Raw: %s') % raw[:500])

        json_str = match.group()

        # Try direct parse first
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass

        # Fix common AI JSON issues:
        # 1. Trailing commas before } or ]
        json_str = re.sub(r',\s*([}\]])', r'\1', json_str)
        # 2. Single quotes instead of double quotes
        json_str = re.sub(r"(?<!\\)'", '"', json_str)
        # 3. Unescaped newlines inside strings
        json_str = re.sub(r'(?<=[^\\])\n', ' ', json_str)
        # 4. Control characters
        json_str = re.sub(r'[\x00-\x1f\x7f]', ' ', json_str)

        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            # Last resort: try to extract arrays manually and build minimal result
            _logger.warning("JSON parse failed after cleanup: %s", e)
            _logger.warning("Raw JSON (first 1000): %s", json_str[:1000])

            # Try to salvage partial data
            try:
                # Extract just chart_of_accounts array
                coa_match = re.search(r'"chart_of_accounts"\s*:\s*(\[.*?\])\s*,', json_str, re.DOTALL)
                oe_match = re.search(r'"opening_entries"\s*:\s*(\[.*?\])', json_str, re.DOTALL)

                result = {
                    'analysis_summary': 'Partial parse — some data may be missing',
                    'company_name': '',
                    'fiscal_year_start': str(fields.Date.today()),
                    'total_accounts': 0,
                    'total_debit': 0.0,
                    'total_credit': 0.0,
                    'is_balanced': False,
                    'warnings': [f'JSON parse error: {e}. Partial data extracted.'],
                    'chart_of_accounts': [],
                    'opening_entries': [],
                }

                if coa_match:
                    # Clean and parse the COA array
                    coa_str = re.sub(r',\s*]', ']', coa_match.group(1))
                    coa_str = re.sub(r',\s*([}\]])', r'\1', coa_str)
                    try:
                        result['chart_of_accounts'] = json.loads(coa_str)
                    except Exception:
                        pass

                if oe_match:
                    oe_str = re.sub(r',\s*]', ']', oe_match.group(1))
                    oe_str = re.sub(r',\s*([}\]])', r'\1', oe_str)
                    try:
                        result['opening_entries'] = json.loads(oe_str)
                    except Exception:
                        pass

                if result['chart_of_accounts'] or result['opening_entries']:
                    return result

            except Exception as salvage_err:
                _logger.error("Salvage also failed: %s", salvage_err)

            raise UserError(_(
                'AI returned malformed JSON. '
                'Try reducing the input data size or paste less accounts at once. '
                'Error: %s'
            ) % str(e))

    # ── Excel File Generator ──────────────────────────────────────
    def _generate_excel_files(self, ai_result):
        """Generate COA and Opening Entries — Excel if openpyxl available, else CSV."""
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
            self._generate_with_openpyxl(ai_result, Workbook, Font, PatternFill, Alignment, Border, Side)
        except ImportError:
            _logger.warning("openpyxl not available — generating CSV files instead")
            self._generate_csv_files(ai_result)
        return

    def _generate_csv_files(self, ai_result):
        """Fallback: generate CSV files when openpyxl is not installed."""
        import csv as csv_mod

        coa_data = ai_result.get('chart_of_accounts', [])
        oe_data  = ai_result.get('opening_entries', [])

        # ── COA CSV ───────────────────────────────────────────────
        coa_buf = io.StringIO()
        writer  = csv_mod.writer(coa_buf)
        writer.writerow(['code','name','account_type','reconcile',
                         'deprecated','group_id/complete_name','note'])
        for acc in coa_data:
            writer.writerow([
                acc.get('code',''),
                acc.get('name',''),
                acc.get('account_type','asset_current'),
                'TRUE' if acc.get('reconcile') else 'FALSE',
                'TRUE' if acc.get('deprecated') else 'FALSE',
                acc.get('group_id/complete_name',''),
                acc.get('note',''),
            ])
        coa_bytes = coa_buf.getvalue().encode('utf-8-sig')
        self.coa_file     = base64.b64encode(coa_bytes)
        self.coa_filename = f'COA_{self.client_id.name or "Client"}_{fields.Date.today()}.csv'
        self.coa_count    = len(coa_data)

        # ── OE CSV ────────────────────────────────────────────────
        oe_buf  = io.StringIO()
        writer2 = csv_mod.writer(oe_buf)
        writer2.writerow(['date','ref','journal_id/name',
                          'line_ids/account_id/code','line_ids/name',
                          'line_ids/debit','line_ids/credit'])
        total_d = total_c = 0.0
        for entry in oe_data:
            d = float(entry.get('line_ids/debit',  0) or 0)
            c = float(entry.get('line_ids/credit', 0) or 0)
            total_d += d
            total_c += c
            writer2.writerow([
                entry.get('date', str(fields.Date.today())),
                entry.get('ref', 'OE/2024/001'),
                entry.get('journal_id/name', 'Opening Entries'),
                str(entry.get('line_ids/account_id/code', '')),
                entry.get('line_ids/name', 'Opening Balance'),
                d, c,
            ])
        oe_bytes = oe_buf.getvalue().encode('utf-8-sig')
        self.oe_file      = base64.b64encode(oe_bytes)
        self.oe_filename  = f'OE_{self.client_id.name or "Client"}_{fields.Date.today()}.csv'
        self.oe_count     = len(oe_data)
        self.total_debit  = total_d
        self.total_credit = total_c
        self.is_balanced  = abs(total_d - total_c) < 0.01

    def _generate_with_openpyxl(self, ai_result, Workbook, Font, PatternFill, Alignment, Border, Side):
        """Generate formatted Excel files using openpyxl."""
        coa_data = ai_result.get('chart_of_accounts', [])
        oe_data = ai_result.get('opening_entries', [])

        # ── File 1: Chart of Accounts ─────────────────────────────
        wb_coa = Workbook()
        ws = wb_coa.active
        ws.title = 'Chart of Accounts'

        # Header style
        header_fill = PatternFill('solid', start_color='1F5C99')
        header_font = Font(bold=True, color='FFFFFF', name='Arial', size=11)
        header_align = Alignment(horizontal='center', vertical='center', wrap_text=True)
        thin = Side(style='thin', color='CCCCCC')
        border = Border(left=thin, right=thin, top=thin, bottom=thin)

        # Instruction row
        ws['A1'] = (
            f'Chart of Accounts — Ready for Odoo {self.odoo_version} Import  |  '
            f'Client: {self.client_id.name if self.client_id else ""}  |  '
            f'Generated by Smart Task Hub'
        )
        ws['A1'].font = Font(bold=True, color='1F5C99', name='Arial', size=11)
        ws.merge_cells(f'A1:{chr(64 + len(COA_COLUMNS))}1')
        ws.row_dimensions[1].height = 22

        # Column headers (row 2) — exact Odoo import names
        headers = ['code', 'name', 'account_type', 'reconcile',
                   'deprecated', 'group_id/complete_name', 'note']
        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=2, column=col, value=h)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_align
            cell.border = border

        ws.row_dimensions[2].height = 20

        # Data rows
        alt_fill = PatternFill('solid', start_color='EBF3FB')
        for row_idx, acc in enumerate(coa_data, 3):
            row_data = [
                str(acc.get('code', '')),
                acc.get('name', ''),
                acc.get('account_type', 'asset_current'),
                'TRUE' if acc.get('reconcile') else 'FALSE',
                'TRUE' if acc.get('deprecated') else 'FALSE',
                acc.get('group_id/complete_name', ''),
                acc.get('note', ''),
            ]
            for col, val in enumerate(row_data, 1):
                cell = ws.cell(row=row_idx, column=col, value=val)
                cell.font = Font(name='Arial', size=10)
                cell.border = border
                cell.alignment = Alignment(vertical='center')
                if row_idx % 2 == 0:
                    cell.fill = alt_fill

        # Column widths
        widths = [12, 40, 25, 12, 12, 30, 25]
        for col, w in enumerate(widths, 1):
            ws.column_dimensions[ws.cell(row=2, column=col).column_letter].width = w

        ws.freeze_panes = 'A3'

        # Add validation note sheet
        ws_note = wb_coa.create_sheet('Import Instructions')
        ws_note['A1'] = 'HOW TO IMPORT IN ODOO'
        ws_note['A1'].font = Font(bold=True, size=13, color='1F5C99')
        instructions = [
            '', '1. Go to: Accounting > Configuration > Chart of Accounts',
            '2. Click: Action > Import Records',
            '3. Upload this Excel file (Chart of Accounts sheet)',
            '4. Map columns if needed (they should auto-map)',
            '5. Click Import',
            '',
            'IMPORTANT NOTES:',
            '- account_type must match exactly (see valid values below)',
            '- reconcile=TRUE is required for receivable/payable accounts',
            '- deprecated=TRUE means header/group account (no transactions)',
            '',
            'VALID account_type VALUES:',
        ]
        for i, line in enumerate(instructions, 2):
            ws_note[f'A{i}'] = line
        row = len(instructions) + 2
        for at in ACCOUNT_TYPES:
            ws_note[f'A{row}'] = f'  • {at}'
            row += 1
        ws_note.column_dimensions['A'].width = 55

        # Save COA to binary
        coa_buffer = io.BytesIO()
        wb_coa.save(coa_buffer)
        coa_buffer.seek(0)

        self.coa_file = base64.b64encode(coa_buffer.read())
        self.coa_filename = f'COA_{self.client_id.name or "Client"}_{fields.Date.today()}.xlsx'
        self.coa_count = len(coa_data)

        # ── File 2: Opening Entries ───────────────────────────────
        wb_oe = Workbook()
        ws2 = wb_oe.active
        ws2.title = 'Opening Entries'

        ws2['A1'] = (
            f'Opening Journal Entries — Ready for Odoo {self.odoo_version} Import  |  '
            f'Client: {self.client_id.name if self.client_id else ""}  |  '
            f'Generated by Smart Task Hub'
        )
        ws2['A1'].font = Font(bold=True, color='1F5C99', name='Arial', size=11)
        ws2.merge_cells(f'A1:{chr(64 + len(OE_COLUMNS))}1')
        ws2.row_dimensions[1].height = 22

        oe_headers = ['date', 'ref', 'journal_id/name',
                      'line_ids/account_id/code', 'line_ids/name',
                      'line_ids/debit', 'line_ids/credit']
        for col, h in enumerate(oe_headers, 1):
            cell = ws2.cell(row=2, column=col, value=h)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_align
            cell.border = border

        ws2.row_dimensions[2].height = 20

        total_debit = 0.0
        total_credit = 0.0

        for row_idx, entry in enumerate(oe_data, 3):
            debit = float(entry.get('line_ids/debit', 0) or 0)
            credit = float(entry.get('line_ids/credit', 0) or 0)
            total_debit += debit
            total_credit += credit

            row_data = [
                entry.get('date', str(fields.Date.today())),
                entry.get('ref', 'OE/2024/001'),
                entry.get('journal_id/name', 'Opening Entries'),
                str(entry.get('line_ids/account_id/code', '')),
                entry.get('line_ids/name', 'Opening Balance'),
                debit,
                credit,
            ]
            for col, val in enumerate(row_data, 1):
                cell = ws2.cell(row=row_idx, column=col, value=val)
                cell.font = Font(name='Arial', size=10)
                cell.border = border
                cell.alignment = Alignment(vertical='center')
                if row_idx % 2 == 0:
                    cell.fill = alt_fill
                # Number format for debit/credit
                if col in (6, 7):
                    cell.number_format = '#,##0.00'

        # Totals row
        total_row = len(oe_data) + 3
        ws2.cell(row=total_row, column=5, value='TOTAL').font = Font(bold=True, name='Arial')
        for col, val in [(6, total_debit), (7, total_credit)]:
            cell = ws2.cell(row=total_row, column=col, value=val)
            cell.font = Font(bold=True, name='Arial',
                             color='198754' if abs(total_debit - total_credit) < 0.01 else 'DC3545')
            cell.number_format = '#,##0.00'
            cell.fill = PatternFill('solid', start_color='D6EAF8')

        # Balanced check
        balance_cell = ws2.cell(row=total_row + 1, column=5)
        if abs(total_debit - total_credit) < 0.01:
            balance_cell.value = '✅ BALANCED'
            balance_cell.font = Font(bold=True, color='198754', name='Arial')
        else:
            diff = total_debit - total_credit
            balance_cell.value = f'⚠️ DIFFERENCE: {diff:,.2f}'
            balance_cell.font = Font(bold=True, color='DC3545', name='Arial')

        oe_widths = [14, 18, 20, 25, 35, 16, 16]
        for col, w in enumerate(oe_widths, 1):
            ws2.column_dimensions[ws2.cell(row=2, column=col).column_letter].width = w

        ws2.freeze_panes = 'A3'

        # Import instructions sheet
        ws2_note = wb_oe.create_sheet('Import Instructions')
        ws2_note['A1'] = 'HOW TO IMPORT OPENING ENTRIES IN ODOO'
        ws2_note['A1'].font = Font(bold=True, size=13, color='1F5C99')
        oe_instructions = [
            '',
            '1. First create the journal: Accounting > Configuration > Journals',
            '   Name: "Opening Entries", Type: Miscellaneous',
            '',
            '2. Go to: Accounting > Accounting > Journal Entries',
            '3. Click: Action > Import Records',
            '4. Upload this file (Opening Entries sheet)',
            '5. Map columns and click Import',
            '6. Review and Post all imported entries',
            '',
            'IMPORTANT:',
            '- Total Debit MUST equal Total Credit before posting',
            '- Use the date = first day of your fiscal year',
            '- Do NOT post until Chart of Accounts is fully imported',
        ]
        for i, line in enumerate(oe_instructions, 2):
            ws2_note[f'A{i}'] = line
        ws2_note.column_dimensions['A'].width = 60

        oe_buffer = io.BytesIO()
        wb_oe.save(oe_buffer)
        oe_buffer.seek(0)

        self.oe_file = base64.b64encode(oe_buffer.read())
        self.oe_filename = f'OE_{self.client_id.name or "Client"}_{fields.Date.today()}.xlsx'
        self.oe_count = len(oe_data)
        self.total_debit = total_debit
        self.total_credit = total_credit
        self.is_balanced = abs(total_debit - total_credit) < 0.01

    def _update_analysis_html(self, ai_result):
        """Build analysis HTML to show in form."""
        warnings = ai_result.get('warnings', [])
        warn_html = ''
        if warnings:
            warn_html = '<div style="background:#fff3cd;border-left:4px solid #ffc107;padding:10px;margin:10px 0;">'
            warn_html += '<strong>⚠️ Warnings:</strong><ul>'
            for w in warnings:
                warn_html += f'<li>{w}</li>'
            warn_html += '</ul></div>'

        balanced_color = '#198754' if self.is_balanced else '#dc3545'
        balanced_text = 'Balanced ✅' if self.is_balanced else f'NOT balanced ⚠️ (diff: {self.total_debit - self.total_credit:,.2f})'

        self.ai_analysis = f"""
        <div style="font-family:Arial,sans-serif;padding:16px;">
            <h4 style="color:#1F5C99;border-bottom:2px solid #1F5C99;padding-bottom:6px;">
                AI Analysis Summary
            </h4>
            <p>{ai_result.get('analysis_summary', '')}</p>
            {warn_html}
            <table style="width:100%;border-collapse:collapse;margin-top:12px;">
                <tr style="background:#1F5C99;color:white;">
                    <th style="padding:8px;text-align:left;">Item</th>
                    <th style="padding:8px;text-align:right;">Value</th>
                </tr>
                <tr style="background:#EBF3FB;">
                    <td style="padding:8px;">Total Accounts</td>
                    <td style="padding:8px;text-align:right;font-weight:bold;">{self.coa_count}</td>
                </tr>
                <tr>
                    <td style="padding:8px;">Opening Entry Lines</td>
                    <td style="padding:8px;text-align:right;font-weight:bold;">{self.oe_count}</td>
                </tr>
                <tr style="background:#EBF3FB;">
                    <td style="padding:8px;">Total Debit</td>
                    <td style="padding:8px;text-align:right;">{self.total_debit:,.2f}</td>
                </tr>
                <tr>
                    <td style="padding:8px;">Total Credit</td>
                    <td style="padding:8px;text-align:right;">{self.total_credit:,.2f}</td>
                </tr>
                <tr style="background:#EBF3FB;">
                    <td style="padding:8px;">Balance Status</td>
                    <td style="padding:8px;text-align:right;font-weight:bold;color:{balanced_color};">
                        {balanced_text}
                    </td>
                </tr>
            </table>
            <p style="margin-top:16px;color:#6c757d;font-size:12px;">
                Download the Excel files below and import them into Odoo.
                See the "Import Instructions" sheet in each file for step-by-step guidance.
            </p>
        </div>
        """
