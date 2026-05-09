import { _t } from "@web/core/l10n/translation";
import { formatCurrency } from "@web/core/currency";
import { roundPrecision } from "@web/core/utils/numbers";
import { parseFloat as parseFieldFloat } from "@web/views/fields/parsers";
import { patch } from "@web/core/utils/patch";
import { NumberPopup } from "@point_of_sale/app/components/popups/number_popup/number_popup";
import { enhancedButtons } from "@point_of_sale/app/components/numpad/numpad";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { PaymentScreenPaymentLines } from "@point_of_sale/app/screens/payment_screen/payment_lines/payment_lines";
import { PaymentScreenStatus } from "@point_of_sale/app/screens/payment_screen/payment_status/payment_status";
import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { PosOrderAccounting } from "@point_of_sale/app/models/accounting/pos_order_accounting";
import { PosOrderlineAccounting } from "@point_of_sale/app/models/accounting/pos_order_line_accounting";
import { PosPayment } from "@point_of_sale/app/models/pos_payment";
import { ProductTemplateAccounting } from "@point_of_sale/app/models/accounting/product_template_accounting";

function convertCurrencyAmount(amount, fromCurrency, toCurrency) {
    if (!fromCurrency || !toCurrency || fromCurrency.id === toCurrency.id) {
        return amount;
    }
    if (fromCurrency.rate && toCurrency.rate) {
        return amount * (toCurrency.rate / fromCurrency.rate);
    }
    return amount;
}

function roundCurrency(amount, currency) {
    return currency?.round ? currency.round(amount || 0) : amount || 0;
}

function formatInCurrency(amount, currency) {
    return formatCurrency(roundCurrency(amount, currency), currency.id);
}

function getPricelistCurrency(pricelist, fallbackCurrency) {
    return pricelist?.currency_id || fallbackCurrency;
}

function getAirportCurrency(order) {
    if (!order?.config?.airport_currency_mode) {
        return order.currency;
    }
    return order.airport_currency_id || getPricelistCurrency(order.pricelist_id, order.currency);
}

function orderUsesAirportCurrency(order) {
    const currency = getAirportCurrency(order);
    return Boolean(order?.config?.airport_currency_mode && currency && currency.id !== order.currency.id);
}

function paymentAirportCurrency(payment) {
    const order = payment.pos_order_id;
    const methodCurrency = payment.payment_method_id?.airport_currency_id;
    if (methodCurrency) {
        return methodCurrency;
    }
    if (order?.config?.airport_auto_payment_currency) {
        return getAirportCurrency(order);
    }
    return order?.currency;
}

function getForeignToPosRate(currency, order) {
    return convertCurrencyAmount(1, currency, order.currency);
}

patch(ProductTemplateAccounting.prototype, {
    getPrice(
        pricelist,
        quantity,
        price_extra = 0,
        recurring = false,
        variant = false,
        original_line = false,
        related_lines = [],
        outputCurrency = false
    ) {
        if (recurring && !pricelist) {
            alert(
                _t(
                    "An error occurred when loading product prices. " +
                        "Make sure all pricelists are available in the POS."
                )
            );
        }

        const config = this.models["pos.config"].getFirst();
        const posCurrency = config.currency_id;
        const targetCurrency = outputCurrency || posCurrency;
        const product = variant;
        const productTmpl = variant.product_tmpl_id || this;
        const standardPrice = variant ? variant.standard_price : this.standard_price;
        const basePrice = variant ? variant.lst_price : this.list_price;
        let price = basePrice + (price_extra || 0);
        let priceCurrency = posCurrency;

        if (!pricelist) {
            return convertCurrencyAmount(price, priceCurrency, targetCurrency);
        }

        if (original_line && original_line.isLotTracked() && product) {
            related_lines.push(
                ...original_line.order_id.lines.filter((line) => line.product_id.id == product.id)
            );
            quantity = related_lines.reduce((sum, line) => sum + line.getQuantity(), 0);
        }

        const tmplRules = (productTmpl.backLink("<-product.pricelist.item.product_tmpl_id") || [])
            .filter((rule) => rule.pricelist_id.id === pricelist.id && !rule.product_id)
            .sort((a, b) => b.min_quantity - a.min_quantity);
        const productRules = (product?.backLink?.("<-product.pricelist.item.product_id") || [])
            .filter((rule) => rule.pricelist_id.id === pricelist.id)
            .sort((a, b) => b.min_quantity - a.min_quantity);

        const tmplRulesSet = new Set(tmplRules.map((rule) => rule.id));
        const productRulesSet = new Set(productRules.map((rule) => rule.id));
        const generalRulesIds = pricelist.getGeneralRulesIdsByCategories(this.parentCategories);
        const rules = this.models["product.pricelist.item"]
            .readMany([...productRulesSet, ...tmplRulesSet, ...generalRulesIds])
            .filter((rule) => rule.min_quantity <= quantity);

        const rule = rules.length && rules[0];
        if (!rule) {
            return convertCurrencyAmount(price, priceCurrency, targetCurrency);
        }

        const ruleCurrency = rule.currency_id || getPricelistCurrency(pricelist, posCurrency);
        if (rule.base === "pricelist") {
            if (rule.base_pricelist_id) {
                priceCurrency = getPricelistCurrency(rule.base_pricelist_id, posCurrency);
                price = this.getPrice(
                    rule.base_pricelist_id,
                    quantity,
                    0,
                    true,
                    variant,
                    false,
                    [],
                    priceCurrency
                );
            }
        } else if (rule.base === "standard_price") {
            price = standardPrice;
            priceCurrency = posCurrency;
        }

        if (rule.compute_price === "fixed") {
            price = rule.fixed_price;
            priceCurrency = ruleCurrency;
        } else {
            price = convertCurrencyAmount(price, priceCurrency, ruleCurrency);
            priceCurrency = ruleCurrency;

            if (rule.compute_price === "percentage") {
                price = price - price * (rule.percent_price / 100);
            } else {
                const priceLimit = price;
                price -= price * (rule.price_discount / 100);
                if (rule.price_round) {
                    price = roundPrecision(price, rule.price_round);
                }
                if (rule.price_surcharge) {
                    price += rule.price_surcharge;
                }
                if (rule.price_min_margin) {
                    price = Math.max(price, priceLimit + rule.price_min_margin);
                }
                if (rule.price_max_margin) {
                    price = Math.min(price, priceLimit + rule.price_max_margin);
                }
            }
        }

        return convertCurrencyAmount(price, priceCurrency, targetCurrency);
    },
});

patch(PosOrderAccounting.prototype, {
    get currencyDisplayPrice() {
        if (this.airportUsesForeignCurrency?.()) {
            return this.getAirportDisplayAmount(this.displayPrice);
        }
        return super.currencyDisplayPrice;
    },

    get currencyDisplayPriceIncl() {
        if (this.airportUsesForeignCurrency?.()) {
            return this.getAirportDisplayAmount(this.priceIncl);
        }
        return super.currencyDisplayPriceIncl;
    },

    get currencyDisplayPriceExcl() {
        if (this.airportUsesForeignCurrency?.()) {
            return this.getAirportDisplayAmount(this.priceExcl);
        }
        return super.currencyDisplayPriceExcl;
    },

    get currencyAmountTaxes() {
        if (this.airportUsesForeignCurrency?.()) {
            return this.getAirportDisplayAmount(this.amountTaxes);
        }
        return super.currencyAmountTaxes;
    },

    setOrderPrices() {
        super.setOrderPrices(...arguments);
        this._syncAirportOrderAmounts?.();
        for (const line of this.lines) {
            line._syncAirportLineAmounts?.();
        }
        for (const payment of this.payment_ids) {
            payment._syncAirportPaymentFromBase?.();
        }
    },
});

patch(PosOrder.prototype, {
    setup(vals) {
        super.setup(...arguments);
        this.airport_currency_id = vals.airport_currency_id || this.airport_currency_id || false;
        this.airport_amount_untaxed = vals.airport_amount_untaxed || 0;
        this.airport_amount_tax = vals.airport_amount_tax || 0;
        this.airport_amount_total = vals.airport_amount_total || 0;
        this.airport_amount_paid = vals.airport_amount_paid || 0;
        this.airport_amount_return = vals.airport_amount_return || 0;
        this.airport_exchange_rate = vals.airport_exchange_rate || 0;
        this.airport_exchange_rate_date = vals.airport_exchange_rate_date || false;
        this._syncAirportCurrencyFromPricelist();
    },

    setPricelist(pricelist) {
        super.setPricelist(...arguments);
        this._syncAirportCurrencyFromPricelist();
        this._syncAirportOrderAmounts();
        for (const line of this.lines) {
            line._syncAirportLineAmounts?.();
        }
    },

    addPaymentline(paymentMethod) {
        const result = super.addPaymentline(...arguments);
        if (result.status) {
            const line = result.data;
            line._ensureAirportPaymentCurrency();
            line._syncAirportPaymentFromBase();
        }
        return result;
    },

    airportUsesForeignCurrency() {
        return orderUsesAirportCurrency(this);
    },

    getAirportCurrency() {
        return getAirportCurrency(this);
    },

    convertBaseToAirport(amount) {
        return roundCurrency(convertCurrencyAmount(amount, this.currency, this.getAirportCurrency()), this.getAirportCurrency());
    },

    convertAirportToBase(amount, currency = false) {
        const airportCurrency = currency || this.getAirportCurrency();
        return roundCurrency(convertCurrencyAmount(amount, airportCurrency, this.currency), this.currency);
    },

    getAirportDisplayAmount(baseAmount) {
        return formatInCurrency(this.convertBaseToAirport(baseAmount), this.getAirportCurrency());
    },

    getAirportDisplayTotalDue() {
        return this.getAirportDisplayAmount(this.totalDue);
    },

    getAirportDisplayRemainingDue() {
        return this.getAirportDisplayAmount(this.remainingDue);
    },

    getAirportDisplayChange() {
        return this.getAirportDisplayAmount(this.change);
    },

    getAirportDisplayBaseEquivalent() {
        return formatCurrency(this.totalDue, this.currency.id);
    },

    _syncAirportCurrencyFromPricelist() {
        if (!this.config?.airport_currency_mode) {
            return;
        }
        const currency = getPricelistCurrency(this.pricelist_id, this.currency);
        this.airport_currency_id = currency;
        this.airport_exchange_rate = getForeignToPosRate(currency, this);
        this.airport_exchange_rate_date = luxon.DateTime.now().toISODate();
    },

    _syncAirportOrderAmounts() {
        if (!this.config?.airport_currency_mode || !this.airport_currency_id) {
            return;
        }
        this.airport_amount_untaxed = this.convertBaseToAirport(this.priceExcl);
        this.airport_amount_tax = this.convertBaseToAirport(this.amountTaxes);
        this.airport_amount_total = this.convertBaseToAirport(this.priceIncl);
        this.airport_amount_paid = this.convertBaseToAirport(this.amountPaid);
        this.airport_amount_return = this.convertBaseToAirport(this.change);
        this.airport_exchange_rate = getForeignToPosRate(this.airport_currency_id, this);
        this.airport_exchange_rate_date = luxon.DateTime.now().toISODate();
    },
});

patch(PosOrderlineAccounting.prototype, {
    get currencyDisplayPrice() {
        if (this.order_id?.airportUsesForeignCurrency?.()) {
            if (this.combo_parent_id) {
                return "";
            }
            if (this.getDiscount() === 100) {
                return _t("Free");
            }
            return this.getAirportDisplayAmount(this.displayPrice);
        }
        return super.currencyDisplayPrice;
    },

    get currencyDisplayPriceUnit() {
        if (this.order_id?.airportUsesForeignCurrency?.()) {
            return this.getAirportDisplayAmount(this.displayPriceUnit);
        }
        return super.currencyDisplayPriceUnit;
    },

    getAirportDisplayAmount(baseAmount) {
        const currency = this.order_id.getAirportCurrency();
        const amount = roundCurrency(convertCurrencyAmount(baseAmount, this.currency, currency), currency);
        return formatInCurrency(amount, currency);
    },

    _syncAirportLineAmounts() {
        const order = this.order_id;
        if (!order?.config?.airport_currency_mode || !order.airport_currency_id) {
            return;
        }
        const currency = order.getAirportCurrency();
        this.airport_currency_id = currency;
        this.airport_price_unit = order.convertBaseToAirport(this.displayPriceUnit);
        this.airport_price_subtotal = order.convertBaseToAirport(this.priceExcl);
        this.airport_price_subtotal_incl = order.convertBaseToAirport(this.priceIncl);
        this.airport_exchange_rate = getForeignToPosRate(currency, order);
    },
});

patch(PosPayment.prototype, {
    setup(vals) {
        super.setup(...arguments);
        this.airport_currency_id = vals.airport_currency_id || this.airport_currency_id || false;
        this.airport_amount = vals.airport_amount || 0;
        this.airport_exchange_rate = vals.airport_exchange_rate || 0;
        this.airport_exchange_rate_date = vals.airport_exchange_rate_date || false;
        this._ensureAirportPaymentCurrency();
        if (!this.airport_amount && this.amount) {
            this._syncAirportPaymentFromBase();
        }
    },

    setAmount(value) {
        super.setAmount(...arguments);
        this._syncAirportPaymentFromBase();
    },

    _ensureAirportPaymentCurrency() {
        const currency = paymentAirportCurrency(this);
        if (this.pos_order_id?.config?.airport_currency_mode && currency) {
            this.airport_currency_id = currency;
            this.airport_exchange_rate = getForeignToPosRate(currency, this.pos_order_id);
            this.airport_exchange_rate_date = luxon.DateTime.now().toISODate();
        }
    },

    airportUsesForeignCurrency() {
        return Boolean(
            this.pos_order_id?.config?.airport_currency_mode &&
                this.airport_currency_id &&
                this.airport_currency_id.id !== this.pos_order_id.currency.id
        );
    },

    convertAirportToBase(amount) {
        this._ensureAirportPaymentCurrency();
        return this.pos_order_id.convertAirportToBase(amount, this.airport_currency_id);
    },

    setAirportAmount(amount) {
        this._ensureAirportPaymentCurrency();
        if (!this.airport_currency_id) {
            this.setAmount(amount);
            return;
        }
        this.airport_amount = roundCurrency(amount, this.airport_currency_id);
        this.airport_exchange_rate = getForeignToPosRate(this.airport_currency_id, this.pos_order_id);
        this.airport_exchange_rate_date = luxon.DateTime.now().toISODate();
        this.amount = this.pos_order_id.currency.round(this.airport_amount * this.airport_exchange_rate);
    },

    _syncAirportPaymentFromBase() {
        this._ensureAirportPaymentCurrency();
        if (!this.airport_currency_id) {
            return;
        }
        this.airport_amount = roundCurrency(
            convertCurrencyAmount(this.amount || 0, this.pos_order_id.currency, this.airport_currency_id),
            this.airport_currency_id
        );
        this.airport_exchange_rate = getForeignToPosRate(this.airport_currency_id, this.pos_order_id);
        this.airport_exchange_rate_date = luxon.DateTime.now().toISODate();
    },

    getAirportDisplayAmount() {
        if (!this.airport_currency_id) {
            return "";
        }
        return formatInCurrency(this.airport_amount || 0, this.airport_currency_id);
    },

    getAirportBaseEquivalentLabel() {
        if (!this.airportUsesForeignCurrency()) {
            return "";
        }
        return formatCurrency(this.getAmount(), this.pos_order_id.currency.id);
    },
});

patch(PaymentScreen.prototype, {
    async addNewPaymentLine(paymentMethod) {
        const result = await super.addNewPaymentLine(...arguments);
        const line = this.selectedPaymentLine;
        if (result && line?.airportUsesForeignCurrency?.()) {
            this.numberBuffer.set((line.airport_amount || 0).toString());
        }
        return result;
    },

    updateSelectedPaymentline(amount = false) {
        const line = this.selectedPaymentLine;
        if (!line?.airportUsesForeignCurrency?.()) {
            return super.updateSelectedPaymentline(...arguments);
        }

        let tenderAmount = amount;
        if (tenderAmount === false) {
            if (this.numberBuffer.get() === null) {
                tenderAmount = null;
            } else if (this.numberBuffer.get() === "") {
                tenderAmount = 0;
            } else {
                tenderAmount = this.numberBuffer.getFloat();
            }
        }

        if (tenderAmount === null) {
            return super.updateSelectedPaymentline(null);
        }

        const parsedAmount =
            typeof tenderAmount === "number" ? tenderAmount : parseFieldFloat(tenderAmount);
        const baseAmount = line.convertAirportToBase(parsedAmount || 0);
        const result = super.updateSelectedPaymentline(baseAmount);
        line.setAirportAmount(parsedAmount || 0);
        return result;
    },
});

patch(PaymentScreenStatus.prototype, {
    get amountText() {
        if (this.order?.airportUsesForeignCurrency?.()) {
            return !this.isRemaining
                ? this.order.getAirportDisplayChange()
                : this.order.getAirportDisplayRemainingDue();
        }
        return super.amountText;
    },
});

patch(PaymentScreenPaymentLines.prototype, {
    async selectLine(paymentline) {
        if (!this.ui.isSmall || !paymentline.airportUsesForeignCurrency?.()) {
            return super.selectLine(...arguments);
        }
        this.props.selectLine(paymentline.uuid);
        this.dialog.add(NumberPopup, {
            title: _t("Tender amount"),
            buttons: enhancedButtons(),
            startingValue: paymentline.airport_amount || 0,
            getPayload: (num) => {
                this.props.updateSelectedPaymentline(parseFieldFloat(num));
            },
        });
    },
});
