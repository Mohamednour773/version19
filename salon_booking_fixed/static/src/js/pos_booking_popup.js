/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { rpc } from "@web/core/network/rpc";
import { Dialog } from "@web/core/dialog/dialog";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";

console.log("[SalonBooking] ✅ JS module loaded successfully");

// ── Helpers ───────────────────────────────────────────────────────────────────

function zpad(n) { return String(n).padStart(2, "0"); }

function toDateStr(d) {
    return `${d.getFullYear()}-${zpad(d.getMonth()+1)}-${zpad(d.getDate())}`;
}

function buildUpcomingDays(n = 14) {
    const days = [], today = new Date();
    const dayNames = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"];
    const monNames = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    for (let i = 0; i < n; i++) {
        const d = new Date(today);
        d.setDate(today.getDate() + i);
        const label =
            i === 0 ? `Today (${monNames[d.getMonth()]} ${d.getDate()})` :
            i === 1 ? `Tomorrow (${monNames[d.getMonth()]} ${d.getDate()})` :
            `${dayNames[d.getDay()]} ${monNames[d.getMonth()]} ${d.getDate()}`;
        days.push({ value: toDateStr(d), label });
    }
    return days;
}

// ══════════════════════════════════════════════════════════════════════════════
//  SalonBookingDialog
// ══════════════════════════════════════════════════════════════════════════════

export class SalonBookingDialog extends Component {
    static template  = "salon_booking.SalonBookingDialog";
    static components = { Dialog };
    static props = {
        product:           { type: Object },
        onBookingConfirmed:{ type: Function },
        close:             { type: Function },
    };

    setup() {
        this.pos          = usePos();
        this.notification = useService("notification");
        this.upcomingDays = buildUpcomingDays(14);
        this.state = useState({
            step:     "booking",
            loading:  false,
            error:    null,
            employees:          [],
            slots:              [],
            appointmentTypeId:  null,
            slotDuration:       30,
            selectedEmployee:   null,
            selectedDate:       this.upcomingDays[0].value,
            selectedSlot:       null,
            customerId:         null,
            customerName:       "",
        });
        onWillStart(() => this._fetchProductData());
    }

    async _fetchProductData() {
        this.state.loading = true;
        this.state.error   = null;
        try {
            const res = await rpc("/salon/pos/get_employees", {
                product_tmpl_id: this.props.product.id,
            });
            this.state.employees         = res.employees          || [];
            this.state.appointmentTypeId = res.appointment_type_id || null;
            this.state.slotDuration      = res.slot_duration       || 30;
        } catch {
            this.state.error = "Could not load employee list. Please try again.";
        } finally {
            this.state.loading = false;
        }
    }

    async _fetchSlots() {
        if (!this.state.selectedEmployee || !this.state.selectedDate || !this.state.appointmentTypeId) return;
        this.state.loading = true; this.state.error = null; this.state.slots = []; this.state.selectedSlot = null;
        try {
            const res = await rpc("/salon/pos/get_slots", {
                appointment_type_id: this.state.appointmentTypeId,
                employee_id:         this.state.selectedEmployee.id,
                date:                this.state.selectedDate,
                slot_duration:       this.state.slotDuration,
            });
            this.state.slots = (res.slots || []).filter(s => s.available);
            if (!this.state.slots.length) this.state.error = "No available slots on this date.";
        } catch {
            this.state.error = "Could not load available slots.";
        } finally {
            this.state.loading = false;
        }
    }

    async selectEmployee(emp) {
        this.state.selectedEmployee = emp;
        this.state.error = null;
        await this._fetchSlots();
    }
    async selectDate(value) {
        this.state.selectedDate = value;
        this.state.slots = [];
        this.state.selectedSlot = null;
        this.state.error = null;
        await this._fetchSlots();
    }
    selectSlot(slot)    { this.state.selectedSlot = slot; this.state.error = null; }

    async goToStep(step) {
        this.state.error = null;
        if (step === "date" && !this.state.selectedEmployee) { this.state.error = "Please select a barber first."; return; }
        if (step === "slot") {
            if (!this.state.selectedDate) { this.state.error = "Please select a date first."; return; }
            await this._fetchSlots();
            if (!this.state.error) this.state.step = "slot";
            return;
        }
        if (step === "confirm") {
            if (!this.state.selectedSlot) { this.state.error = "Please select a time slot first."; return; }
            const order = this.pos.getOrder();
            const client = order && order.getPartner();
            this.state.customerId   = client ? client.id   : null;
            this.state.customerName = client ? client.name : "Walk-In Customer";
        }
        this.state.step = step;
    }

    async confirmBooking() {
        this.state.loading = true; this.state.error = null;
        const order  = this.pos.getOrder();
        const client = order && order.getPartner();
        let orderLineId = null;
        let orderLine = null;
        if (order) {
            const lines = order.lines;
            orderLine = [...lines].reverse().find(l => l.product_id?.id === this.props.product.id);
            if (orderLine) orderLineId = orderLine.uuid || orderLine.id;
        }
        let res;
        try {
            res = await rpc("/salon/pos/book", {
                appointment_type_id: this.state.appointmentTypeId,
                employee_id:         this.state.selectedEmployee.id,
                start_iso:           this.state.selectedSlot.start_iso,
                end_iso:             this.state.selectedSlot.end_iso,
                partner_id:          client ? client.id : null,
                pos_order_line_id:   orderLineId,
            });
        } catch (error) {
            console.error("[SalonBooking] POS booking RPC failed", error);
            this.state.error = "Network error. Please retry.";
            this.state.loading = false;
            return;
        }

        if (res.success) {
            try {
                if (orderLine) {
                    if (typeof orderLine.update === "function") {
                        orderLine.update({
                            salon_appointment_id: res.appointment_id,
                            salon_pos_order_line_uuid: orderLineId,
                        });
                    } else {
                        orderLine.salon_appointment_id = res.appointment_id;
                        orderLine.salon_pos_order_line_uuid = orderLineId;
                    }
                }
            } catch (error) {
                console.warn("[SalonBooking] Booking was created, but POS line metadata was not updated.", error);
            }
            this.state.step = "done";
            this.props.onBookingConfirmed({ appointmentId: res.appointment_id, employeeName: this.state.selectedEmployee.name, slot: this.state.selectedSlot });
        } else {
            const message = res.message || "Booking failed. Please choose another time.";
            this.state.selectedSlot = null;
            await this._fetchSlots();
            this.state.error = message;
        }
        this.state.loading = false;
    }

    closeDialog() { this.props.close(); }

    get stepTitle() {
        return { booking:"Book Appointment", employee:"Step 1 - Select Barber", date:"Step 2 - Select Date", slot:"Step 3 - Select Time", confirm:"Step 4 - Confirm", done:"Booking Confirmed!" }[this.state.step] || "";
    }
    get formattedSelectedDate() {
        const found = this.upcomingDays.find(d => d.value === this.state.selectedDate);
        return found ? found.label : (this.state.selectedDate || "");
    }
    get selectedSlotLabel() {
        const s = this.state.selectedSlot;
        return s ? `${s.start} – ${s.end}` : "";
    }
}

// ══════════════════════════════════════════════════════════════════════════════
//  Patch ProductScreen
// ══════════════════════════════════════════════════════════════════════════════

patch(ProductScreen.prototype, {
    setup() {
        super.setup();
        this.dialog       = useService("dialog");
        this.notification = useService("notification");
    },

    async addProductToOrder(product) {
        await super.addProductToOrder(product);

        console.log("[SalonBooking] addProductToOrder called for:", product.display_name,
                    "| salon_is_bookable:", product.salon_is_bookable);

        if (!product.salon_is_bookable) return;

        console.log("[SalonBooking] Opening booking dialog...");

        this.dialog.add(SalonBookingDialog, {
            product,
            onBookingConfirmed: (info) => {
                this.notification.add(
                    `Appointment booked with ${info.employeeName} at ${info.slot.start}`,
                    { type: "success", title: "Salon Booking Confirmed" }
                );
            },
        });
    },
});

console.log("[SalonBooking] ✅ ProductScreen patched successfully");
