/** @odoo-module **/

import { OrderReceipt } from "@point_of_sale/app/screens/receipt_screen/receipt/order_receipt";
import { ClubReceiptSection } from "@club_management_pos_ui/components/club_receipt_section/club_receipt_section";

/**
 * Register ClubReceiptSection as a sub-component of OrderReceipt so that
 * the template extension (order_receipt.xml) can reference it by name.
 *
 * We deliberately do NOT patch setup() here.  Patching setup() onto an
 * existing component's prototype is unreliable in Odoo 19's OWL 3 — the
 * hook registration system (useState / useEffect) only works reliably
 * inside a setup() that belongs to an OWL component class definition.
 *
 * All data-fetching logic lives in ClubReceiptSection which owns its own
 * setup(), exactly like CustomerInfoCard does for the product screen.
 */
OrderReceipt.components = {
    ...OrderReceipt.components,
    ClubReceiptSection,
};
