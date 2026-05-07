/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { rpc } from "@web/core/network/rpc";

const STEP_ORDER = ["service", "employee", "slot", "customer"];

function zpad(value) {
    return String(value).padStart(2, "0");
}

function toDateStr(date) {
    return `${date.getFullYear()}-${zpad(date.getMonth() + 1)}-${zpad(date.getDate())}`;
}

function upcomingDays(count = 14) {
    const today = new Date();
    return [...Array(count)].map((_, index) => {
        const date = new Date(today);
        date.setDate(today.getDate() + index);
        return {
            value: toDateStr(date),
            label: index === 0
                ? "Today"
                : date.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" }),
        };
    });
}

publicWidget.registry.SalonBookingWebsite = publicWidget.Widget.extend({
    selector: ".o_salon_booking_app",
    events: {
        "click [data-service-id]": "_onService",
        "click [data-employee-id]": "_onEmployee",
        "click [data-day]": "_onDay",
        "click [data-slot]": "_onSlot",
        "click [data-action='back']": "_onBack",
        "submit [data-role='booking-form']": "_onSubmit",
    },

    async start() {
        this.state = {
            step: "service",
            service: null,
            employee: null,
            day: toDateStr(new Date()),
            slot: null,
        };
        this.days = upcomingDays();
        this.el.querySelector("[data-role='days']").innerHTML = this.days.map((day) => `
            <div class="col-6 col-md-3">
                <button type="button" class="btn btn-outline-secondary w-100" data-day="${day.value}">
                    ${day.label}
                </button>
            </div>
        `).join("");
        await this._loadServices();
        this._renderStep();
        return Promise.resolve();
    },

    async _json(route, params = {}) {
        return rpc(route, {
            csrf_token: this.el.dataset.csrfToken || "",
            ...params,
        });
    },

    _setError(message) {
        const target = this.el.querySelector("[data-role='error']");
        target.textContent = message || "";
        target.classList.toggle("d-none", !message);
    },

    _setSuccess(message) {
        const target = this.el.querySelector("[data-role='success']");
        target.textContent = message || "";
        target.classList.toggle("d-none", !message);
    },

    async _loadServices() {
        this._setError("");
        const target = this.el.querySelector("[data-role='services']");
        target.innerHTML = `<div class="col-12 text-muted">Loading services...</div>`;
        try {
            const response = await this._json("/salon/get_services");
            this.services = response.services || [];
            target.innerHTML = this.services.length ? this.services.map((service) => `
                <div class="col-md-6">
                    <button type="button" class="o_salon_service_tile" data-service-id="${service.id}">
                        <img src="${service.image_url}" alt="${service.name}"/>
                        <span>
                            <strong>${service.name}</strong>
                            <small>${service.duration} min</small>
                        </span>
                    </button>
                </div>
            `).join("") : `<div class="col-12 alert alert-info">No bookable services are available.</div>`;
        } catch {
            target.innerHTML = "";
            this._setError("Could not load services. Please try again.");
        }
    },

    async _loadEmployees() {
        const target = this.el.querySelector("[data-role='employees']");
        target.innerHTML = `<div class="col-12 text-muted">Loading barbers...</div>`;
        const response = await this._json("/salon/get_employees", {
            appointment_type_id: this.state.service.appointment_type_id,
        });
        this.employees = response.employees || [];
        target.innerHTML = this.employees.length ? this.employees.map((employee) => `
            <div class="col-md-4 col-6">
                <button type="button" class="o_salon_employee_tile" data-employee-id="${employee.id}">
                    <img src="${employee.image_url}" alt="${employee.name}"/>
                    <strong>${employee.name}</strong>
                    <small>${employee.job_title || ""}</small>
                </button>
            </div>
        `).join("") : `<div class="col-12 alert alert-warning">No barbers are configured for this service.</div>`;
    },

    async _loadSlots() {
        const target = this.el.querySelector("[data-role='slots']");
        target.innerHTML = `<div class="col-12 text-muted">Loading available times...</div>`;
        const response = await this._json("/salon/get_slots", {
            appointment_type_id: this.state.service.appointment_type_id,
            employee_id: this.state.employee.id,
            date: this.state.day,
        });
        this.slots = (response.slots || []).filter((slot) => slot.available);
        target.innerHTML = this.slots.length ? this.slots.map((slot, index) => `
            <div class="col-6 col-md-3">
                <button type="button" class="btn btn-outline-secondary w-100" data-slot="${index}">
                    ${slot.start} - ${slot.end}
                </button>
            </div>
        `).join("") : `<div class="col-12 alert alert-warning">No available slots on this date.</div>`;
    },

    _renderStep() {
        for (const step of STEP_ORDER) {
            this.el.querySelector(`[data-step='${step}']`).classList.toggle("d-none", step !== this.state.step);
            this.el.querySelector(`[data-step-pill='${step}']`).classList.toggle("active", step === this.state.step);
        }
        if (this.state.step === "done") {
            for (const step of STEP_ORDER) {
                this.el.querySelector(`[data-step='${step}']`).classList.add("d-none");
                this.el.querySelector(`[data-step-pill='${step}']`).classList.remove("active");
            }
            this.el.querySelector("[data-role='nav']").classList.add("d-none");
            return;
        }
        this.el.querySelector("[data-role='nav'] [data-action='back']")
            .classList.toggle("d-none", this.state.step === "service");
    },

    _go(step) {
        this.state.step = step;
        this._setError("");
        this._renderStep();
    },

    async _onService(ev) {
        const id = Number(ev.currentTarget.dataset.serviceId);
        this.state.service = this.services.find((service) => service.id === id);
        this.state.employee = null;
        this.state.slot = null;
        await this._loadEmployees();
        this._go("employee");
    },

    async _onEmployee(ev) {
        const id = Number(ev.currentTarget.dataset.employeeId);
        this.state.employee = this.employees.find((employee) => employee.id === id);
        this.state.slot = null;
        await this._loadSlots();
        this._go("slot");
    },

    async _onDay(ev) {
        this.state.day = ev.currentTarget.dataset.day;
        this.state.slot = null;
        await this._loadSlots();
    },

    _onSlot(ev) {
        const index = Number(ev.currentTarget.dataset.slot);
        this.state.slot = this.slots[index];
        this.el.querySelector("[data-role='summary']").textContent =
            `${this.state.service.name} with ${this.state.employee.name} on ${this.state.day} at ${this.state.slot.start}`;
        this._go("customer");
    },

    _onBack() {
        const current = STEP_ORDER.indexOf(this.state.step);
        this._go(STEP_ORDER[Math.max(current - 1, 0)]);
    },

    async _onSubmit(ev) {
        ev.preventDefault();
        if (!this.state.service || !this.state.employee || !this.state.slot) {
            this._setError("Please complete service, barber, and time selection.");
            return;
        }
        const form = new FormData(ev.currentTarget);
        const payload = {
            appointment_type_id: this.state.service.appointment_type_id,
            employee_id: this.state.employee.id,
            start_iso: this.state.slot.start_iso,
            end_iso: this.state.slot.end_iso,
            customer_name: form.get("customer_name"),
            customer_mobile: form.get("customer_mobile"),
            customer_email: form.get("customer_email"),
        };
        const response = await this._json("/salon/book", payload);
        if (response.success) {
            this._setError("");
            this._setSuccess(response.message || "Your appointment has been confirmed.");
            this.state.step = "done";
            this._renderStep();
            ev.currentTarget.classList.add("d-none");
        } else {
            const message = response.message || "Booking failed. Please try another time.";
            this.state.slot = null;
            await this._loadSlots();
            this._go("slot");
            this._setError(message);
        }
    },
});
