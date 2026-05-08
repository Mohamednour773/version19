import { _t } from "@web/core/l10n/translation";
import { parseFloat as parseFieldFloat } from "@web/views/fields/parsers";
import { patch } from "@web/core/utils/patch";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { NumberPopup } from "@point_of_sale/app/components/popups/number_popup/number_popup";
import { SelectionPopup } from "@point_of_sale/app/components/popups/selection_popup/selection_popup";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { PosPayment } from "@point_of_sale/app/models/pos_payment";

patch(PosPayment.prototype, {
    setup(vals) {
        super.setup(...arguments);
        this.payment_currency_id = vals.payment_currency_id || false;
        this.foreign_amount = vals.foreign_amount || 0;
        this.exchange_rate = vals.exchange_rate || 0;
        this.exchange_rate_date = vals.exchange_rate_date || false;
    },

    setMultiCurrencyPayment(currency, foreignAmount, exchangeRate) {
        this.pos_order_id.assertEditable();
        this.payment_currency_id = currency;
        this.foreign_amount = foreignAmount;
        this.exchange_rate = exchangeRate;
        this.exchange_rate_date = luxon.DateTime.now().toISODate();
        this.setAmount(foreignAmount * exchangeRate);
    },

    getMultiCurrencyLabel() {
        if (!this.payment_currency_id) {
            return "";
        }
        const amount = this.foreign_amount || 0;
        return `${amount.toFixed(this.payment_currency_id.decimal_places)} ${this.payment_currency_id.name}`;
    },
});

patch(PaymentScreen.prototype, {
    get acceptedPaymentCurrencies() {
        const config = this.pos.config;
        if (!config.multi_currency_payment) {
            return [];
        }
        return config.multi_currency_ids || [];
    },

    get showMultiCurrencyButton() {
        return this.acceptedPaymentCurrencies.length > 0 && Boolean(this.selectedPaymentLine);
    },

    async selectMultiCurrencyPayment() {
        if (!this.selectedPaymentLine) {
            return;
        }
        const choices = this.acceptedPaymentCurrencies.map((currency) => ({
            id: currency.id,
            label: `${currency.name} ${currency.symbol || ""}`.trim(),
            item: currency,
        }));
        const currency = await makeAwaitable(this.dialog, SelectionPopup, {
            title: _t("Payment Currency"),
            list: choices,
        });
        if (!currency) {
            return;
        }

        const dueInCurrency = this._convertPosAmountToCurrency(
            this.currentOrder.remainingDue || this.selectedPaymentLine.getAmount(),
            currency
        );
        const amount = await makeAwaitable(this.dialog, NumberPopup, {
            title: _t("Foreign Amount"),
            startingValue: dueInCurrency.toFixed(currency.decimal_places),
            formatDisplayedValue: (value) => `${currency.symbol || currency.name} ${value}`,
        });
        if (amount === undefined || amount === "") {
            return;
        }

        const foreignAmount = parseFieldFloat(amount);
        if (!Number.isFinite(foreignAmount) || foreignAmount === 0) {
            this.notification.add(_t("Enter a valid foreign amount."), { type: "warning" });
            return;
        }

        const exchangeRate = this._getForeignToPosRate(currency);
        this.selectedPaymentLine.setMultiCurrencyPayment(currency, foreignAmount, exchangeRate);
        this.numberBuffer.set(this.selectedPaymentLine.getAmount().toString());
    },

    _getForeignToPosRate(currency) {
        const posCurrency = this.pos.currency;
        if (currency.id === posCurrency.id) {
            return 1;
        }
        if (currency.rate && posCurrency.rate) {
            return posCurrency.rate / currency.rate;
        }
        return 1;
    },

    _convertPosAmountToCurrency(amount, currency) {
        const rate = this._getForeignToPosRate(currency);
        return rate ? amount / rate : amount;
    },
});
