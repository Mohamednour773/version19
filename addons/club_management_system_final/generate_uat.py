"""
UAT Checklist Generator for Sports Club / Swimming Academy Management System (Odoo 17)
Generates a professional Word document with Arabic/English mixed content.
"""

from docx import Document
from docx.shared import Pt, RGBColor, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import copy
from datetime import date

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def set_cell_bg(cell, hex_color):
    """Set table cell background color."""
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), hex_color)
    tcPr.append(shd)

def set_cell_borders(cell, color="CCCCCC"):
    """Apply thin borders to a cell."""
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcBorders = OxmlElement('w:tcBorders')
    for side in ['top', 'left', 'bottom', 'right']:
        border = OxmlElement(f'w:{side}')
        border.set(qn('w:val'), 'single')
        border.set(qn('w:sz'), '4')
        border.set(qn('w:space'), '0')
        border.set(qn('w:color'), color)
        tcBorders.append(border)
    tcPr.append(tcBorders)

def cell_para(cell, text, bold=False, font_size=9, color=None,
              align=WD_ALIGN_PARAGRAPH.LEFT, italic=False, rtl=False):
    """Write text into a cell with formatting."""
    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    p = cell.paragraphs[0]
    p.alignment = align
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(2)
    if rtl:
        pPr = p._p.get_or_add_pPr()
        bidi = OxmlElement('w:bidi')
        pPr.append(bidi)
    run = p.add_run(text)
    run.bold = bold
    run.italic = italic
    run.font.size = Pt(font_size)
    if color:
        run.font.color.rgb = RGBColor(*bytes.fromhex(color))
    if rtl:
        rPr = run._r.get_or_add_rPr()
        rtl_elem = OxmlElement('w:rtl')
        rPr.append(rtl_elem)

def add_heading(doc, text, level=1, color_hex="1B4F72"):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(10 if level == 1 else 6)
    p.paragraph_format.space_after = Pt(4)
    run = p.add_run(text)
    run.bold = True
    run.font.size = Pt(16 if level == 1 else 13 if level == 2 else 11)
    run.font.color.rgb = RGBColor(*bytes.fromhex(color_hex))
    return p

def add_para(doc, text, bold=False, size=10, color_hex=None, italic=False,
             align=WD_ALIGN_PARAGRAPH.LEFT, space_before=2, space_after=2):
    p = doc.add_paragraph()
    p.alignment = align
    p.paragraph_format.space_before = Pt(space_before)
    p.paragraph_format.space_after = Pt(space_after)
    run = p.add_run(text)
    run.bold = bold
    run.italic = italic
    run.font.size = Pt(size)
    if color_hex:
        run.font.color.rgb = RGBColor(*bytes.fromhex(color_hex))
    return p

def add_hr(doc, color="1B4F72", size=12):
    """Add a horizontal rule paragraph."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(4)
    pPr = p._p.get_or_add_pPr()
    pBdr = OxmlElement('w:pBdr')
    bottom = OxmlElement('w:bottom')
    bottom.set(qn('w:val'), 'single')
    bottom.set(qn('w:sz'), str(size))
    bottom.set(qn('w:space'), '1')
    bottom.set(qn('w:color'), color)
    pBdr.append(bottom)
    pPr.append(pBdr)

# Column widths in inches for the main UAT table (total ~9.5 inches landscape)
# ID | Test Action (EN) | Arabic Note | Expected Result | Actual Result | Status
COL_W = [0.5, 2.4, 1.8, 2.5, 1.5, 0.8]

HEADER_BG   = "1B4F72"   # deep navy
SECTION_BG  = "D6EAF8"   # light blue section row
ALT_ROW_BG  = "EBF5FB"   # very light blue alternating
WHITE       = "FFFFFF"

STATUS_COLORS = {
    "Pass":    "1E8449",
    "Fail":    "C0392B",
    "Blocked": "D68910",
}

# ─────────────────────────────────────────────
# UAT DATA
# ─────────────────────────────────────────────

SECTIONS = [
    # ─── ROLE: SYSTEM ADMINISTRATOR / MANAGER ─────────────────────────────────
    {
        "role": "SYSTEM ADMINISTRATOR / MANAGER  |  مدير النظام",
        "role_color": "154360",
        "sections": [
            {
                "title": "SECTION 1 — Setup & Configuration  |  الإعداد والتهيئة",
                "items": [
                    {
                        "id": "CFG-01",
                        "action": "Create a new Branch named 'Main Branch' with address and contact details.",
                        "arabic": "إنشاء فرع جديد باسم 'الفرع الرئيسي' مع العنوان والتفاصيل",
                        "expected": "Branch is saved and appears in the branch list with correct details.",
                    },
                    {
                        "id": "CFG-02",
                        "action": "Add a second branch 'North Campus' and assign separate staff to it.",
                        "arabic": "إضافة فرع ثانٍ 'الحرم الشمالي' وتعيين موظفين له",
                        "expected": "Second branch is created; staff assignment is saved correctly.",
                    },
                    {
                        "id": "CFG-03",
                        "action": "Create a trainer profile with name, specialization, commission rate (15%), and linked branch.",
                        "arabic": "إنشاء ملف مدرب مع الاسم والتخصص ونسبة العمولة (15%) والفرع",
                        "expected": "Trainer profile is saved; commission rate is displayed correctly.",
                    },
                    {
                        "id": "CFG-04",
                        "action": "Add a facility (e.g. 'Olympic Pool') with capacity 30 and operating hours 06:00–22:00.",
                        "arabic": "إضافة منشأة 'حوض أولمبي' بسعة 30 وساعات عمل 6 صباحاً–10 مساءً",
                        "expected": "Facility is saved; capacity and hours are shown on the facility card.",
                    },
                    {
                        "id": "CFG-05",
                        "action": "Create a membership package: 'Monthly Swimming – 8 sessions' priced at 500 SAR.",
                        "arabic": "إنشاء باقة اشتراك: 'سباحة شهرية – 8 جلسات' بسعر 500 ريال",
                        "expected": "Package appears in the package list with correct session count and price.",
                    },
                    {
                        "id": "CFG-06",
                        "action": "Create a 'Kids Beginner Swimming' class: 45 min, max 10 students, assigned to Olympic Pool.",
                        "arabic": "إنشاء فصل 'سباحة الأطفال المبتدئين': 45 دقيقة، 10 طلاب كحد أقصى، حوض أولمبي",
                        "expected": "Class is created with correct duration, capacity, and linked facility.",
                    },
                    {
                        "id": "CFG-07",
                        "action": "Set weekly session limit to 3 sessions per member on a specific package.",
                        "arabic": "تحديد حد أقصى 3 جلسات أسبوعياً لباقة معينة",
                        "expected": "Weekly limit is saved; system enforces this limit on booking.",
                    },
                    {
                        "id": "CFG-08",
                        "action": "Configure a rental item: 'Lane 2 – Private' at 80 SAR/hour.",
                        "arabic": "إعداد عنصر إيجار: 'مسار 2 – خاص' بسعر 80 ريال/ساعة",
                        "expected": "Rental item is saved and available in the booking calendar.",
                    },
                ],
            },
            {
                "title": "SECTION 8 — Multi-Branch Access Control  |  التحكم في الوصول متعدد الفروع",
                "items": [
                    {
                        "id": "ACC-01",
                        "action": "Log in as a receptionist assigned to 'Main Branch' only. Try to view 'North Campus' data.",
                        "arabic": "تسجيل دخول كموظف استقبال مرتبط بـ'الفرع الرئيسي' ومحاولة رؤية بيانات الفرع الآخر",
                        "expected": "North Campus data is hidden; receptionist can only see Main Branch records.",
                    },
                    {
                        "id": "ACC-02",
                        "action": "Log in as a Manager with 'All Branches' access. Open both branch dashboards.",
                        "arabic": "تسجيل دخول كمدير بصلاحية 'جميع الفروع' وفتح لوحة تحكم كل فرع",
                        "expected": "Manager sees data from all branches with correct aggregation.",
                    },
                    {
                        "id": "ACC-03",
                        "action": "Attempt to assign a trainer from 'North Campus' to a class in 'Main Branch'.",
                        "arabic": "محاولة تعيين مدرب من الفرع الشمالي لفصل في الفرع الرئيسي",
                        "expected": "System warns or blocks the cross-branch assignment; or allows with manager override only.",
                    },
                    {
                        "id": "ACC-04",
                        "action": "Create a new user role 'Branch Supervisor' with read-only access to reports.",
                        "arabic": "إنشاء دور مستخدم 'مشرف فرع' بصلاحية قراءة فقط للتقارير",
                        "expected": "Role is created; supervisor can view reports but cannot edit any records.",
                    },
                ],
            },
            {
                "title": "SECTION 9 — Reports  |  التقارير",
                "items": [
                    {
                        "id": "RPT-01",
                        "action": "Open the Daily Cash Report for today. Verify total receipts match payments entered.",
                        "arabic": "فتح تقرير النقد اليومي لليوم الحالي والتحقق من تطابق الإجماليات",
                        "expected": "Report shows itemized payments; total matches sum of invoices paid today.",
                    },
                    {
                        "id": "RPT-02",
                        "action": "Generate Trainer Revenue Report for the current month. Filter by a specific trainer.",
                        "arabic": "إنشاء تقرير إيرادات المدربين للشهر الحالي وتصفيته لمدرب معين",
                        "expected": "Report shows total sessions, members trained, and earned commission for that trainer.",
                    },
                    {
                        "id": "RPT-03",
                        "action": "Open Facility Utilization Report. Check which pool/facility is most used this week.",
                        "arabic": "فتح تقرير استخدام المنشآت ومعرفة أكثر المنشآت استخداماً هذا الأسبوع",
                        "expected": "Report shows utilization percentage per facility with peak hours highlighted.",
                    },
                    {
                        "id": "RPT-04",
                        "action": "Export any report to PDF. Verify formatting and branding (logo, date, branch name).",
                        "arabic": "تصدير أي تقرير إلى PDF والتحقق من التنسيق والشعار والتاريخ واسم الفرع",
                        "expected": "PDF is generated with correct layout, club logo, and report date.",
                    },
                    {
                        "id": "RPT-05",
                        "action": "Run Membership Expiry Report to list members whose subscriptions expire within 7 days.",
                        "arabic": "تشغيل تقرير انتهاء الاشتراكات لعرض الأعضاء المنتهية اشتراكاتهم خلال 7 أيام",
                        "expected": "List shows member name, package, expiry date, and contact info for follow-up.",
                    },
                ],
            },
            {
                "title": "SECTION 6 — Trainer Commission Flow  |  تدفق عمولة المدرب",
                "items": [
                    {
                        "id": "COM-01",
                        "action": "After a trainer completes 5 sessions, open their commission summary for the month.",
                        "arabic": "بعد اكتمال 5 جلسات للمدرب، فتح ملخص عمولته للشهر",
                        "expected": "System shows sessions count, total revenue generated, and calculated commission amount.",
                    },
                    {
                        "id": "COM-02",
                        "action": "Change a trainer's commission rate from 15% to 20%. Verify new sessions use the updated rate.",
                        "arabic": "تغيير نسبة عمولة المدرب من 15% إلى 20% والتحقق من تطبيقها على الجلسات الجديدة",
                        "expected": "New sessions reflect 20% rate; old sessions retain 15% rate.",
                    },
                    {
                        "id": "COM-03",
                        "action": "Mark trainer commission as 'Paid' and enter payment reference number.",
                        "arabic": "تحديد عمولة المدرب كـ'مدفوعة' وإدخال رقم مرجع الدفع",
                        "expected": "Commission record is updated to 'Paid' status with reference; locked from further edit.",
                    },
                    {
                        "id": "COM-04",
                        "action": "Cancel a session that had already been used for commission calculation. Check if commission adjusts.",
                        "arabic": "إلغاء جلسة تم احتسابها ضمن العمولة والتحقق من تعديل المبلغ تلقائياً",
                        "expected": "Commission amount is automatically recalculated after session cancellation.",
                    },
                ],
            },
        ],
    },
    # ─── ROLE: RECEPTIONIST ───────────────────────────────────────────────────
    {
        "role": "RECEPTIONIST  |  موظف الاستقبال",
        "role_color": "1A5276",
        "sections": [
            {
                "title": "SECTION 2 — Client Registration  |  تسجيل العملاء",
                "items": [
                    {
                        "id": "REG-01",
                        "action": "Register a new adult client: full name, phone, email, date of birth, national ID.",
                        "arabic": "تسجيل عميل بالغ جديد: الاسم الكامل، الهاتف، البريد، تاريخ الميلاد، رقم الهوية",
                        "expected": "Client profile is created with a unique ID; all fields saved correctly.",
                    },
                    {
                        "id": "REG-02",
                        "action": "Register a child client (age 8) and link them to an existing parent account.",
                        "arabic": "تسجيل طفل (عمر 8 سنوات) وربطه بحساب ولي أمر موجود",
                        "expected": "Child profile is created; parent-child relationship is displayed on both profiles.",
                    },
                    {
                        "id": "REG-03",
                        "action": "Register a new parent and simultaneously create two child profiles under them.",
                        "arabic": "تسجيل ولي أمر جديد وإنشاء ملفين لطفلين تحته في نفس الوقت",
                        "expected": "Parent and both children are saved; children appear under parent's account.",
                    },
                    {
                        "id": "REG-04",
                        "action": "Upload a profile photo for a client.",
                        "arabic": "رفع صورة شخصية لعميل",
                        "expected": "Photo is saved and displayed on the client card and check-in screen.",
                    },
                    {
                        "id": "REG-05",
                        "action": "Search for a client by phone number. Verify the correct profile appears.",
                        "arabic": "البحث عن عميل برقم الهاتف والتحقق من ظهور الملف الصحيح",
                        "expected": "Search returns the correct client; partial phone number search also works.",
                    },
                    {
                        "id": "REG-06",
                        "action": "Edit an existing client's email address and save.",
                        "arabic": "تعديل عنوان البريد الإلكتروني لعميل موجود وحفظ التغيير",
                        "expected": "New email is saved; change is logged in the client's activity history.",
                    },
                ],
            },
            {
                "title": "SECTION 3 — Membership & Payment Flow  |  تدفق الاشتراك والدفع",
                "items": [
                    {
                        "id": "PAY-01",
                        "action": "Assign the 'Monthly Swimming – 8 sessions' package to a client. Set start date as today.",
                        "arabic": "تعيين باقة 'سباحة شهرية – 8 جلسات' لعميل مع تاريخ بدء اليوم",
                        "expected": "Membership is created with correct start/end dates and session counter (0/8).",
                    },
                    {
                        "id": "PAY-02",
                        "action": "Process a cash payment of 500 SAR for the membership. Print the receipt.",
                        "arabic": "معالجة دفع نقدي 500 ريال للاشتراك وطباعة الإيصال",
                        "expected": "Invoice is marked as 'Paid'; receipt is generated with correct amount, date, and cashier name.",
                    },
                    {
                        "id": "PAY-03",
                        "action": "Process a card payment using POS terminal integration.",
                        "arabic": "معالجة دفع بالبطاقة عبر تكامل نقطة البيع",
                        "expected": "Payment is recorded as 'Card'; transaction reference is saved on the invoice.",
                    },
                    {
                        "id": "PAY-04",
                        "action": "Apply a 10% discount to a membership invoice before payment.",
                        "arabic": "تطبيق خصم 10% على فاتورة اشتراك قبل الدفع",
                        "expected": "Discounted amount is shown; discount reason is required and saved.",
                    },
                    {
                        "id": "PAY-05",
                        "action": "Renew an expired membership for an existing client with the same package.",
                        "arabic": "تجديد اشتراك منتهٍ لعميل موجود بنفس الباقة",
                        "expected": "New membership period starts; old membership is archived; payment invoice is generated.",
                    },
                    {
                        "id": "PAY-06",
                        "action": "Issue a refund for a cancelled membership (partial refund for 3 unused sessions).",
                        "arabic": "إصدار استرداد لاشتراك ملغى (استرداد جزئي لـ3 جلسات غير مستخدمة)",
                        "expected": "Refund amount is calculated automatically; credit note is created and linked to original invoice.",
                    },
                    {
                        "id": "PAY-07",
                        "action": "Check membership status of a client who has used 7 out of 8 sessions.",
                        "arabic": "التحقق من حالة اشتراك عميل استهلك 7 من أصل 8 جلسات",
                        "expected": "Membership shows '7/8 sessions used' with a warning; 1 session remaining is clearly visible.",
                    },
                ],
            },
            {
                "title": "SECTION 4 — Session Scheduling & Calendar  |  جدولة الجلسات والتقويم",
                "items": [
                    {
                        "id": "SCH-01",
                        "action": "Open the weekly calendar view. Verify all scheduled classes are displayed correctly.",
                        "arabic": "فتح عرض التقويم الأسبوعي والتحقق من ظهور جميع الفصول المجدولة",
                        "expected": "Calendar shows all classes with trainer name, time, facility, and current enrollment count.",
                    },
                    {
                        "id": "SCH-02",
                        "action": "Book a client into the 'Kids Beginner Swimming' class on Tuesday at 4:00 PM.",
                        "arabic": "حجز عميل في فصل 'سباحة الأطفال المبتدئين' الثلاثاء الساعة 4 مساءً",
                        "expected": "Booking is confirmed; client appears on the class roster; session count is decremented by 1.",
                    },
                    {
                        "id": "SCH-03",
                        "action": "Reschedule a client's session to a different time slot in the same week.",
                        "arabic": "إعادة جدولة جلسة عميل إلى موعد مختلف في نفس الأسبوع",
                        "expected": "Old slot is freed; new slot is booked; client receives notification (if configured).",
                    },
                    {
                        "id": "SCH-04",
                        "action": "Cancel a booked session and check if the session credit is returned to the membership.",
                        "arabic": "إلغاء جلسة محجوزة والتحقق من إعادة رصيد الجلسة إلى الاشتراك",
                        "expected": "Session credit is returned to membership; cancellation reason is logged.",
                    },
                    {
                        "id": "SCH-05",
                        "action": "Set a recurring weekly class every Monday and Wednesday for one month.",
                        "arabic": "إعداد فصل أسبوعي متكرر كل اثنين وأربعاء لمدة شهر",
                        "expected": "All recurring sessions appear on the calendar; modifications to one do not affect others.",
                    },
                ],
            },
            {
                "title": "SECTION 5 — Attendance & Session Completion  |  الحضور وإتمام الجلسات",
                "items": [
                    {
                        "id": "ATT-01",
                        "action": "Mark a client as 'Present' for today's swimming class.",
                        "arabic": "تسجيل حضور عميل في فصل السباحة اليوم",
                        "expected": "Attendance is recorded with timestamp; session is deducted from the client's membership.",
                    },
                    {
                        "id": "ATT-02",
                        "action": "Mark a client as 'Absent' (no-show) for a booked session.",
                        "arabic": "تسجيل غياب عميل عن جلسة محجوزة",
                        "expected": "Absent status is recorded; system shows configurable option to deduct or retain the session.",
                    },
                    {
                        "id": "ATT-03",
                        "action": "Complete the end-of-class process: mark class as 'Done' after all attendance is entered.",
                        "arabic": "إتمام عملية نهاية الفصل: تحديد الفصل كـ'منتهٍ' بعد إدخال الحضور",
                        "expected": "Class status changes to 'Completed'; attendance report is generated; trainer commission is triggered.",
                    },
                    {
                        "id": "ATT-04",
                        "action": "View the attendance history for a specific client over the last 30 days.",
                        "arabic": "عرض سجل الحضور لعميل معين خلال آخر 30 يوماً",
                        "expected": "History shows each session attended, absent, or cancelled with dates and class names.",
                    },
                    {
                        "id": "ATT-05",
                        "action": "Use the quick check-in screen to scan a membership card / QR code for client check-in.",
                        "arabic": "استخدام شاشة تسجيل الدخول السريع لمسح بطاقة العضوية / رمز QR",
                        "expected": "Client name and photo appear; membership status and remaining sessions shown in under 2 seconds.",
                    },
                ],
            },
            {
                "title": "SECTION 7 — Rental Booking  |  حجز الإيجار",
                "items": [
                    {
                        "id": "RNT-01",
                        "action": "Book 'Lane 2 – Private' for a client from 10:00 AM to 11:00 AM tomorrow.",
                        "arabic": "حجز 'المسار 2 – خاص' لعميل من 10 صباحاً إلى 11 صباحاً غداً",
                        "expected": "Booking is created; invoice for 80 SAR (1 hour) is generated automatically.",
                    },
                    {
                        "id": "RNT-02",
                        "action": "View the rental calendar and check availability of all lanes for this week.",
                        "arabic": "عرض تقويم الإيجار والتحقق من توافر جميع المسارات هذا الأسبوع",
                        "expected": "Calendar shows booked/available slots color-coded; clicking a slot shows booking details.",
                    },
                    {
                        "id": "RNT-03",
                        "action": "Cancel a rental booking that is 2 hours in the future.",
                        "arabic": "إلغاء حجز إيجار موعده بعد ساعتين",
                        "expected": "Booking is cancelled; invoice is voided or credit note issued as per cancellation policy.",
                    },
                    {
                        "id": "RNT-04",
                        "action": "Extend an active rental by 30 minutes mid-session.",
                        "arabic": "تمديد إيجار نشط بمقدار 30 دقيقة أثناء الجلسة",
                        "expected": "Booking end time is updated; additional charge of 40 SAR (30 min) is added to the invoice.",
                    },
                ],
            },
        ],
    },
    # ─── ROLE: ACCOUNTANT ─────────────────────────────────────────────────────
    {
        "role": "ACCOUNTANT  |  المحاسب",
        "role_color": "0E6655",
        "sections": [
            {
                "title": "SECTION 3 (Accounting) — Financial Verification  |  التحقق المالي",
                "items": [
                    {
                        "id": "ACC-FIN-01",
                        "action": "Verify that all membership payments today are posted to the correct income account in the ledger.",
                        "arabic": "التحقق من ترحيل جميع مدفوعات الاشتراكات اليوم إلى حساب الإيرادات الصحيح",
                        "expected": "Each payment has a corresponding journal entry; account mapping matches the chart of accounts.",
                    },
                    {
                        "id": "ACC-FIN-02",
                        "action": "Reconcile end-of-day cash drawer against system cash receipts report.",
                        "arabic": "مطابقة درج النقد في نهاية اليوم مع تقرير المقبوضات النقدية في النظام",
                        "expected": "System total matches physical cash; any discrepancy flag is visible and exportable.",
                    },
                    {
                        "id": "ACC-FIN-03",
                        "action": "Check that the refund/credit note issued earlier is correctly reversed in the accounts.",
                        "arabic": "التحقق من انعكاس إشعار الخصم / المرتجع الصادر سابقاً في الحسابات بشكل صحيح",
                        "expected": "Credit note reduces the revenue account correctly; linked to original invoice.",
                    },
                    {
                        "id": "ACC-FIN-04",
                        "action": "Generate a monthly P&L summary filtered by the 'Main Branch'.",
                        "arabic": "إنشاء ملخص الأرباح والخسائر الشهري مصفى حسب 'الفرع الرئيسي'",
                        "expected": "P&L shows revenue, trainer commissions, and net income for the selected branch and period.",
                    },
                    {
                        "id": "ACC-FIN-05",
                        "action": "View outstanding (unpaid) invoices and sort them by due date.",
                        "arabic": "عرض الفواتير غير المسددة وترتيبها حسب تاريخ الاستحقاق",
                        "expected": "List shows client name, invoice amount, due date, and days overdue; exportable to Excel.",
                    },
                    {
                        "id": "ACC-FIN-06",
                        "action": "Apply a VAT (15%) setting to a package and verify the invoice breakdown.",
                        "arabic": "تطبيق إعداد ضريبة القيمة المضافة (15%) على باقة والتحقق من تفاصيل الفاتورة",
                        "expected": "Invoice shows subtotal, VAT amount (15%), and total separately; VAT account mapping is correct.",
                    },
                ],
            },
        ],
    },
    # ─── EDGE CASES ────────────────────────────────────────────────────────────
    {
        "role": "EDGE CASES & NEGATIVE TESTING  |  الحالات الحدية والاختبار السلبي",
        "role_color": "6E2F1A",
        "sections": [
            {
                "title": "SECTION 10 — Edge Cases  |  الحالات الاستثنائية",
                "items": [
                    {
                        "id": "EDG-01",
                        "action": "Try to book a client into a class that is already at full capacity (10/10 students).",
                        "arabic": "محاولة حجز عميل في فصل ممتلئ (10/10 طلاب)",
                        "expected": "System blocks booking with clear error: 'Class is full'. Offers to add to waitlist.",
                    },
                    {
                        "id": "EDG-02",
                        "action": "Book a client into a 4th session in the same week when the weekly limit is 3.",
                        "arabic": "حجز عميل في جلسة رابعة بنفس الأسبوع والحد الأقصى 3 جلسات",
                        "expected": "System blocks the booking with a warning: 'Weekly limit of 3 sessions reached'.",
                    },
                    {
                        "id": "EDG-03",
                        "action": "Try to book a session for a client whose membership has expired.",
                        "arabic": "محاولة حجز جلسة لعميل منتهي اشتراكه",
                        "expected": "System blocks booking; shows membership expiry date and prompts to renew.",
                    },
                    {
                        "id": "EDG-04",
                        "action": "Assign a child client to an adult-only package and attempt to save.",
                        "arabic": "تعيين باقة للبالغين فقط لعميل طفل ومحاولة الحفظ",
                        "expected": "System shows age restriction error and prevents the assignment.",
                    },
                    {
                        "id": "EDG-05",
                        "action": "Try to create two bookings for the same facility at the same time (double-booking test).",
                        "arabic": "محاولة إنشاء حجزين لنفس المنشأة في نفس الوقت (اختبار الحجز المزدوج)",
                        "expected": "Second booking is blocked; system shows 'Facility already booked at this time'.",
                    },
                    {
                        "id": "EDG-06",
                        "action": "Process a payment with amount less than the invoice total (underpayment).",
                        "arabic": "معالجة دفع بمبلغ أقل من إجمالي الفاتورة (دفع ناقص)",
                        "expected": "System records partial payment; invoice status shows 'Partially Paid' with remaining balance.",
                    },
                    {
                        "id": "EDG-07",
                        "action": "Delete a trainer who is currently assigned to active future sessions.",
                        "arabic": "حذف مدرب مرتبط بجلسات مستقبلية نشطة",
                        "expected": "System blocks deletion with message listing the affected sessions; must reassign first.",
                    },
                    {
                        "id": "EDG-08",
                        "action": "Register a client with a duplicate national ID (ID already in the system).",
                        "arabic": "تسجيل عميل برقم هوية مكرر (موجود مسبقاً في النظام)",
                        "expected": "System shows duplicate warning; prevents saving or prompts to merge with existing profile.",
                    },
                    {
                        "id": "EDG-09",
                        "action": "Try to apply a discount greater than the configured maximum (e.g., 60% when max is 50%).",
                        "arabic": "محاولة تطبيق خصم أكبر من الحد الأقصى المحدد (60% والحد 50%)",
                        "expected": "System blocks the discount entry; shows 'Maximum discount is 50%' error.",
                    },
                    {
                        "id": "EDG-10",
                        "action": "Book a session in a facility that is marked as 'Under Maintenance' for that time slot.",
                        "arabic": "حجز جلسة في منشأة محددة كـ'تحت الصيانة' في ذلك الموعد",
                        "expected": "System blocks booking; shows maintenance schedule and suggests alternative facility.",
                    },
                ],
            },
        ],
    },
]

# ─────────────────────────────────────────────
# DOCUMENT BUILDER
# ─────────────────────────────────────────────

def build_document():
    doc = Document()

    # ── Page setup: A4 landscape ──────────────────────────────────────────────
    from docx.oxml import OxmlElement as OXE
    section = doc.sections[0]
    section.page_width  = Cm(29.7)
    section.page_height = Cm(21.0)
    section.left_margin   = Cm(1.5)
    section.right_margin  = Cm(1.5)
    section.top_margin    = Cm(1.5)
    section.bottom_margin = Cm(1.5)
    # Force landscape via XML
    pgSz = section._sectPr.find(qn('w:pgSz'))
    if pgSz is None:
        pgSz = OXE('w:pgSz')
        section._sectPr.append(pgSz)
    pgSz.set(qn('w:orient'), 'landscape')

    # ── TITLE BLOCK ───────────────────────────────────────────────────────────
    # Top rule
    p_rule = doc.add_paragraph()
    p_rule.paragraph_format.space_before = Pt(0)
    p_rule.paragraph_format.space_after  = Pt(0)
    pPr = p_rule._p.get_or_add_pPr()
    pBdr = OxmlElement('w:pBdr')
    top_b = OxmlElement('w:top')
    top_b.set(qn('w:val'),   'single')
    top_b.set(qn('w:sz'),    '24')
    top_b.set(qn('w:space'), '1')
    top_b.set(qn('w:color'), '1B4F72')
    pBdr.append(top_b)
    pPr.append(pBdr)

    add_para(doc, "UAT CHECKLIST — USER ACCEPTANCE TESTING",
             bold=True, size=18, color_hex="1B4F72",
             align=WD_ALIGN_PARAGRAPH.CENTER, space_before=6, space_after=2)

    add_para(doc, "Sports Club & Swimming Academy Management System  |  نظام إدارة النادي الرياضي وأكاديمية السباحة",
             bold=True, size=13, color_hex="2E86C1",
             align=WD_ALIGN_PARAGRAPH.CENTER, space_before=0, space_after=2)

    add_para(doc, "Powered by Odoo 17",
             bold=False, size=10, color_hex="717D7E",
             align=WD_ALIGN_PARAGRAPH.CENTER, space_before=0, space_after=6)

    add_hr(doc, color="1B4F72", size=16)

    # Meta table (project info)
    meta = doc.add_table(rows=2, cols=4)
    meta.style = 'Table Grid'
    meta.alignment = WD_TABLE_ALIGNMENT.CENTER
    col_w_m = [Inches(2.0), Inches(2.5), Inches(2.0), Inches(2.5)]
    meta_data = [
        ["Project / المشروع",    "Sports Club & Swimming Academy",
         "Document Version / الإصدار", "v1.0"],
        ["Prepared By / أعد بواسطة", "QA Team",
         "Test Date / تاريخ الاختبار", date.today().strftime("%d %B %Y")],
    ]
    for ri, row_data in enumerate(meta_data):
        row = meta.rows[ri]
        for ci, text in enumerate(row_data):
            cell = row.cells[ci]
            cell.width = col_w_m[ci]
            is_label = (ci % 2 == 0)
            set_cell_borders(cell, "CCCCCC")
            if is_label:
                set_cell_bg(cell, "D5E8F0")
                cell_para(cell, text, bold=True, font_size=9, color="1B4F72")
            else:
                set_cell_bg(cell, "FFFFFF")
                cell_para(cell, text, bold=False, font_size=9)

    doc.add_paragraph()

    # ── SUMMARY TABLE ─────────────────────────────────────────────────────────
    add_heading(doc, "Test Summary  |  ملخص الاختبار", level=2, color_hex="1A5276")
    add_para(doc,
             "Complete this table at the end of the UAT session. "
             "Count results from all test items and record totals below.",
             italic=True, size=9, color_hex="717D7E")

    summary_headers = ["Total Test Items\nإجمالي بنود الاختبار",
                        "Passed  ناجح", "Failed  فاشل",
                        "Blocked  محجوب", "Not Tested  لم يُختبر",
                        "Pass Rate %\nnسبة النجاح"]
    sum_widths = [Inches(1.8), Inches(1.4), Inches(1.4),
                  Inches(1.4), Inches(1.4), Inches(1.4)]
    sum_table = doc.add_table(rows=2, cols=6)
    sum_table.style = 'Table Grid'
    sum_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    # Header row
    for ci, h in enumerate(summary_headers):
        c = sum_table.rows[0].cells[ci]
        c.width = sum_widths[ci]
        set_cell_bg(c, HEADER_BG)
        set_cell_borders(c, "FFFFFF")
        cell_para(c, h, bold=True, font_size=8, color="FFFFFF", align=WD_ALIGN_PARAGRAPH.CENTER)
    # Data row
    data_values = ["60", "", "", "", "", "_____ %"]
    for ci, val in enumerate(data_values):
        c = sum_table.rows[1].cells[ci]
        c.width = sum_widths[ci]
        set_cell_bg(c, "F0F3F4")
        set_cell_borders(c, "CCCCCC")
        cell_para(c, val, bold=(ci == 0), font_size=10,
                  align=WD_ALIGN_PARAGRAPH.CENTER)

    doc.add_paragraph()
    add_hr(doc, color="2E86C1", size=8)

    # ── LEGEND ────────────────────────────────────────────────────────────────
    add_para(doc,
             "Status Legend:   Pass (P) = Works as expected   |   Fail (F) = Does not work   |   "
             "Blocked (B) = Cannot test (dependency missing)   |   N/T = Not Tested",
             italic=True, size=9, color_hex="555555")
    add_hr(doc, color="CCCCCC", size=4)

    # ── INSTRUCTIONS ─────────────────────────────────────────────────────────
    add_heading(doc, "Testing Instructions  |  تعليمات الاختبار", level=2, color_hex="1A5276")
    instructions = [
        "Each tester should sign the signature sheet at the end of this document.",
        "For each test item, perform the action described and record the actual result.",
        "Mark status as: P (Pass), F (Fail), or B (Blocked).",
        "If a test Fails, add a note in the 'Actual Result' column describing what went wrong.",
        "Do not skip any test item — mark N/T (Not Tested) if time does not permit.",
        "Screenshots of failures should be attached to this document or shared folder.",
    ]
    for inst in instructions:
        p = doc.add_paragraph(style='List Bullet')
        p.paragraph_format.space_before = Pt(1)
        p.paragraph_format.space_after  = Pt(1)
        run = p.add_run(inst)
        run.font.size = Pt(9)

    doc.add_paragraph()

    # ── MAIN TEST SECTIONS ────────────────────────────────────────────────────
    col_headers = ["ID", "Test Action (English)\nالإجراء", "Arabic Note\nملاحظة عربية",
                   "Expected Result\nالنتيجة المتوقعة", "Actual Result\nالنتيجة الفعلية",
                   "Status\nالحالة"]
    col_widths_in = [Inches(w) for w in COL_W]

    total_item_number = 0

    for role_block in SECTIONS:
        # Role banner
        doc.add_paragraph()
        p_role = doc.add_paragraph()
        p_role.paragraph_format.space_before = Pt(8)
        p_role.paragraph_format.space_after  = Pt(4)
        run = p_role.add_run(f"  ROLE: {role_block['role']}  ")
        run.bold = True
        run.font.size = Pt(12)
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        shading_elm = OxmlElement('w:shd')
        shading_elm.set(qn('w:val'),   'clear')
        shading_elm.set(qn('w:color'), 'auto')
        shading_elm.set(qn('w:fill'),  role_block['role_color'])
        p_role._p.get_or_add_pPr().append(shading_elm)

        for sec in role_block['sections']:
            add_heading(doc, sec['title'], level=2, color_hex=role_block['role_color'])

            # Build table
            tbl = doc.add_table(rows=1 + len(sec['items']), cols=6)
            tbl.style = 'Table Grid'
            tbl.alignment = WD_TABLE_ALIGNMENT.LEFT

            # Header row
            hdr_row = tbl.rows[0]
            for ci, hdr_text in enumerate(col_headers):
                cell = hdr_row.cells[ci]
                cell.width = col_widths_in[ci]
                set_cell_bg(cell, HEADER_BG)
                set_cell_borders(cell, "FFFFFF")
                cell_para(cell, hdr_text, bold=True, font_size=8,
                          color="FFFFFF", align=WD_ALIGN_PARAGRAPH.CENTER)

            # Data rows
            for ri, item in enumerate(sec['items']):
                total_item_number += 1
                row = tbl.rows[ri + 1]
                bg = ALT_ROW_BG if ri % 2 == 0 else WHITE

                # ID
                c0 = row.cells[0]
                c0.width = col_widths_in[0]
                set_cell_bg(c0, "D6EAF8")
                set_cell_borders(c0, "AEDCE8")
                cell_para(c0, item['id'], bold=True, font_size=8,
                          color="1B4F72", align=WD_ALIGN_PARAGRAPH.CENTER)

                # Action (EN)
                c1 = row.cells[1]
                c1.width = col_widths_in[1]
                set_cell_bg(c1, bg)
                set_cell_borders(c1, "CCCCCC")
                cell_para(c1, item['action'], font_size=8.5)

                # Arabic note
                c2 = row.cells[2]
                c2.width = col_widths_in[2]
                set_cell_bg(c2, bg)
                set_cell_borders(c2, "CCCCCC")
                cell_para(c2, item['arabic'], font_size=8, italic=True,
                          color="1A5276", rtl=True, align=WD_ALIGN_PARAGRAPH.RIGHT)

                # Expected result
                c3 = row.cells[3]
                c3.width = col_widths_in[3]
                set_cell_bg(c3, bg)
                set_cell_borders(c3, "CCCCCC")
                cell_para(c3, item['expected'], font_size=8.5)

                # Actual result (blank)
                c4 = row.cells[4]
                c4.width = col_widths_in[4]
                set_cell_bg(c4, "FFFFF0")
                set_cell_borders(c4, "CCCCCC")
                cell_para(c4, "", font_size=9)

                # Status (blank)
                c5 = row.cells[5]
                c5.width = col_widths_in[5]
                set_cell_bg(c5, "F9F9F9")
                set_cell_borders(c5, "CCCCCC")
                cell_para(c5, "[ ]", bold=True, font_size=10,
                          color="888888", align=WD_ALIGN_PARAGRAPH.CENTER)

            doc.add_paragraph()

    # ── SIGN-OFF / SIGNATURE SECTION ─────────────────────────────────────────
    doc.add_page_break()
    add_heading(doc, "Sign-Off & Approval  |  التوقيع والاعتماد", level=1, color_hex="1B4F72")
    add_hr(doc, color="1B4F72", size=12)

    add_para(doc,
             "By signing below, the named stakeholder confirms that the UAT has been conducted "
             "and the results are accepted as a basis for Go-Live decision.",
             italic=True, size=10, color_hex="555555", space_after=8)

    sig_data = [
        ["Role / الدور", "Name / الاسم", "Signature / التوقيع", "Date / التاريخ", "Decision"],
        ["Client Representative\nممثل العميل",           "", "_________________", "___/___/______", "[ ] Go Live\n[ ] Conditional\n[ ] Rejected"],
        ["Project Manager\nمدير المشروع",                "", "_________________", "___/___/______", "[ ] Approved\n[ ] Pending"],
        ["Lead Developer\nالمطور الرئيسي",               "", "_________________", "___/___/______", "[ ] Approved\n[ ] Pending"],
        ["QA Tester\nمختبر الجودة",                      "", "_________________", "___/___/______", "[ ] Approved\n[ ] Pending"],
        ["IT Manager (Client Side)\nمدير تقنية المعلومات","", "_________________", "___/___/______", "[ ] Approved\n[ ] Pending"],
    ]

    sig_table = doc.add_table(rows=len(sig_data), cols=5)
    sig_table.style = 'Table Grid'
    sig_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    sig_col_w = [Inches(1.9), Inches(2.2), Inches(1.9), Inches(1.4), Inches(1.5)]

    for ri, row_data in enumerate(sig_data):
        row = sig_table.rows[ri]
        for ci, text in enumerate(row_data):
            c = row.cells[ci]
            c.width = sig_col_w[ci]
            set_cell_borders(c, "AAAAAA")
            if ri == 0:
                set_cell_bg(c, HEADER_BG)
                cell_para(c, text, bold=True, font_size=9, color="FFFFFF",
                          align=WD_ALIGN_PARAGRAPH.CENTER)
            else:
                set_cell_bg(c, "FDFEFE" if ri % 2 == 0 else "FFFFFF")
                cell_para(c, text, font_size=9, align=WD_ALIGN_PARAGRAPH.CENTER)

    doc.add_paragraph()
    add_hr(doc, color="CCCCCC", size=4)

    # ── NOTES SECTION ─────────────────────────────────────────────────────────
    add_heading(doc, "General Notes / Issues  |  ملاحظات عامة / مشاكل", level=2, color_hex="1A5276")
    for _ in range(6):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after  = Pt(0)
        pPr = p._p.get_or_add_pPr()
        pBdr = OxmlElement('w:pBdr')
        bot = OxmlElement('w:bottom')
        bot.set(qn('w:val'),   'single')
        bot.set(qn('w:sz'),    '4')
        bot.set(qn('w:space'), '1')
        bot.set(qn('w:color'), 'AAAAAA')
        pBdr.append(bot)
        pPr.append(pBdr)
        run = p.add_run("  ")
        run.font.size = Pt(14)

    doc.add_paragraph()

    # ── FOOTER NOTE ───────────────────────────────────────────────────────────
    add_hr(doc, color="CCCCCC", size=4)
    add_para(doc,
             f"CONFIDENTIAL — For internal use only.  |  "
             f"سري — للاستخدام الداخلي فقط.    "
             f"Document generated: {date.today().strftime('%d %B %Y')}    "
             f"Total UAT Items: {total_item_number}    Version: 1.0",
             italic=True, size=8, color_hex="AAAAAA",
             align=WD_ALIGN_PARAGRAPH.CENTER)

    return doc, total_item_number


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    output_path = r"D:\جميع ملفات الاكسل\مشاريع CLAUDE\club_management_system\UAT_Checklist_Sports_Club_Odoo17.docx"
    doc, count = build_document()
    doc.save(output_path)
    print(f"Done. {count} UAT items written to:\n{output_path}")
