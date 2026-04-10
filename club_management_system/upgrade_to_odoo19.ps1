# ============================================================
#  Club Management System — Upgrade to Odoo 19
#  Run this script as Administrator
#  PowerShell: Right-click → Run as Administrator
# ============================================================

$src = "D:\جميع ملفات الاكسل\مشاريع CLAUDE\club_management_system"
$dst = "C:\Program Files\Odoo 19\server\odoo\addons\club_management_system"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Club Management — Upgrade to Odoo 19"    -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

# Create destination folder structure
$folders = @(
    "",
    "\models",
    "\views",
    "\wizards",
    "\security",
    "\data"
)
foreach ($f in $folders) {
    $path = "$dst$f"
    if (-not (Test-Path $path)) {
        New-Item -ItemType Directory -Force -Path $path | Out-Null
        Write-Host "Created: $path" -ForegroundColor Yellow
    }
}

# ── Root files ──────────────────────────────────────────────
$rootFiles = @(
    "__manifest__.py",
    "__init__.py"
)
foreach ($f in $rootFiles) {
    Copy-Item "$src\$f" "$dst\$f" -Force
    Write-Host "Copied: $f" -ForegroundColor Green
}

# ── Models ──────────────────────────────────────────────────
$modelFiles = @(
    "__init__.py",
    "club_branch.py",
    "club_trainer.py",
    "club_facility.py",
    "club_package.py",
    "club_membership.py",
    "club_class.py",
    "club_session.py",
    "club_session_trainer.py",
    "club_attendance.py",
    "club_rental.py",
    "club_report.py",
    "res_partner.py"
)
foreach ($f in $modelFiles) {
    Copy-Item "$src\models\$f" "$dst\models\$f" -Force
    Write-Host "Copied: models/$f" -ForegroundColor Green
}

# ── Views ───────────────────────────────────────────────────
$viewFiles = @(
    "club_branch_views.xml",
    "club_trainer_views.xml",
    "club_facility_views.xml",
    "club_package_views.xml",
    "club_membership_views.xml",
    "club_class_views.xml",
    "club_session_views.xml",
    "club_attendance_views.xml",
    "club_rental_views.xml",
    "res_partner_views.xml",
    "club_report_views.xml",
    "club_menus.xml"
)
foreach ($f in $viewFiles) {
    Copy-Item "$src\views\$f" "$dst\views\$f" -Force
    Write-Host "Copied: views/$f" -ForegroundColor Green
}

# ── Wizards ─────────────────────────────────────────────────
$wizardFiles = @(
    "__init__.py",
    "generate_sessions_wizard.py",
    "generate_sessions_wizard_views.xml",
    "reschedule_session_wizard.py",
    "reschedule_session_wizard_views.xml"
)
foreach ($f in $wizardFiles) {
    Copy-Item "$src\wizards\$f" "$dst\wizards\$f" -Force
    Write-Host "Copied: wizards/$f" -ForegroundColor Green
}

# ── Security ────────────────────────────────────────────────
$securityFiles = @(
    "res_groups.xml",
    "ir.model.access.csv",
    "club_security.xml"
)
foreach ($f in $securityFiles) {
    Copy-Item "$src\security\$f" "$dst\security\$f" -Force
    Write-Host "Copied: security/$f" -ForegroundColor Green
}

# ── Data ────────────────────────────────────────────────────
Copy-Item "$src\data\club_data.xml" "$dst\data\club_data.xml" -Force
Write-Host "Copied: data/club_data.xml" -ForegroundColor Green

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  All files copied successfully!"            -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Start Odoo 19 server"                   -ForegroundColor White
Write-Host "  2. Settings → Activate Developer Mode"     -ForegroundColor White
Write-Host "  3. Apps → Search 'Sports Club'"            -ForegroundColor White
Write-Host "  4. Click UPGRADE"                          -ForegroundColor White
Write-Host ""
