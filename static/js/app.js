/* Narcos UI enhancements: dynamic formset rows, searchable selects, dependent
 * batch filtering, and client-side totals previews. Display convenience only —
 * the server's tax engine (docs/tax.py) remains the single authority for
 * stored totals (D32). */

(function () {
  "use strict";

  /* ---------- option snapshots ----------
   * Choices.js rebuilds <option> elements and drops their data-* attributes,
   * so every select's options (value, label, dataset) are captured before
   * enhancement. Prefill, previews, and batch filtering read the snapshot. */

  function snapshotOptions(el) {
    el._opts = Array.prototype.map.call(el.options, function (o) {
      return {
        value: o.value,
        label: (o.textContent || "").trim(),
        data: Object.assign({}, o.dataset),
      };
    });
  }

  function optionData(select, value) {
    if (select._opts) {
      for (var i = 0; i < select._opts.length; i++) {
        if (select._opts[i].value === value) return select._opts[i].data;
      }
      return null;
    }
    var o = select.options[select.selectedIndex];
    return o ? o.dataset : null;
  }

  /* ---------- searchable selects (Choices.js, vendored) ---------- */

  function enhanceSelects(root) {
    if (typeof Choices === "undefined") return;
    root.querySelectorAll("select[data-search]").forEach(function (el) {
      if (el.dataset.enhanced) return;
      el.dataset.enhanced = "1";
      snapshotOptions(el);
      el._choices = new Choices(el, {
        shouldSort: false,
        itemSelectText: "",
        allowHTML: false,
        searchResultLimit: 30,
        searchPlaceholderValue: el.dataset.searchPlaceholder || "",
      });
    });
  }

  /* ---------- dynamic formset rows ---------- */

  function addFormsetRow(prefix) {
    var total = document.getElementById("id_" + prefix + "-TOTAL_FORMS");
    var template = document.getElementById(prefix + "-empty-row");
    var body = document.getElementById(prefix + "-rows");
    if (!total || !template || !body) return;
    var index = parseInt(total.value, 10);
    var holder = document.createElement("tbody");
    holder.innerHTML = template.innerHTML.replaceAll("__prefix__", String(index));
    while (holder.firstElementChild) body.appendChild(holder.firstElementChild);
    total.value = String(index + 1);
    enhanceSelects(body);
    recomputeTotals();
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-add-row]");
    if (button) addFormsetRow(button.dataset.addRow);
  });

  /* ---------- item pick: prefill + batch filtering ---------- */

  function rowInput(row, suffix) {
    return row.querySelector('[name$="-' + suffix + '"]');
  }

  function prefillFromItem(select) {
    var row = select.closest("tr");
    var data = optionData(select, select.value);
    if (!row || !data) return;
    var price = rowInput(row, "unit_price");
    if (price && (!price.value || Number(price.value) === 0) && data.price) {
      price.value = data.price;
    }
    var unitLabel = rowInput(row, "unit_label");
    if (unitLabel && !unitLabel.value && data.baseUnit) {
      unitLabel.value = data.baseUnit;
    }
  }

  function updateBatchHint(batchSelect) {
    var cell = batchSelect.closest("td");
    if (!cell) return;
    var hint = cell.querySelector(".cell-hint");
    var data = batchSelect.value ? optionData(batchSelect, batchSelect.value) : null;
    if (!data) {
      if (hint) hint.remove();
      return;
    }
    if (!hint) {
      hint = document.createElement("span");
      hint.className = "cell-hint";
      cell.appendChild(hint);
    }
    hint.textContent = (data.expiry ? "exp " + data.expiry : "no expiry")
      + " · " + (data.onhand || 0) + " in stock";
  }

  function filterBatches(row) {
    var itemSelect = row.querySelector('select[name$="-item"]');
    var batchSelect = row.querySelector('select[name$="-batch"]');
    if (!itemSelect || !batchSelect || !batchSelect._opts) return;
    var itemValue = itemSelect.value;
    var previous = batchSelect.value;
    var list = batchSelect._opts.filter(function (o) {
      return o.value === "" || !itemValue || o.data.item === itemValue;
    });
    var stillValid = list.some(function (o) { return o.value === previous; });
    if (batchSelect._choices) {
      batchSelect._choices.setChoices(list.map(function (o) {
        return {
          value: o.value,
          label: o.label || "—",
          selected: stillValid ? o.value === previous : o.value === "",
        };
      }), "value", "label", true);
      if (!stillValid) batchSelect._choices.setChoiceByValue("");
    } else {
      batchSelect.innerHTML = "";
      list.forEach(function (o) {
        var opt = document.createElement("option");
        opt.value = o.value;
        opt.textContent = o.label;
        Object.keys(o.data).forEach(function (k) { opt.dataset[k] = o.data[k]; });
        opt.selected = stillValid ? o.value === previous : o.value === "";
        batchSelect.appendChild(opt);
      });
    }
    updateBatchHint(batchSelect);
  }

  /* ---------- amount autofill ----------
   * Prefill a money box only while the user hasn't touched it: empty, or
   * still holding our last prefill. A manual edit (including a split across
   * lines) is never overwritten. */

  function autofill(input, value) {
    if (!input) return;
    var current = input.value;
    if (current === "" || current === "0" || current === input.dataset.autofill) {
      input.value = String(value);
      input.dataset.autofill = String(value);
    }
  }

  function clearAutofill(input) {
    if (input && input.value === input.dataset.autofill) {
      input.value = "";
      delete input.dataset.autofill;
    }
  }

  function firstUntouchedPaymentAmount() {
    var rows = document.querySelectorAll("#payments-rows tr");
    if (!rows.length) return null;
    for (var i = 1; i < rows.length; i++) {
      var other = rowInput(rows[i], "amount");
      if (other && Number(other.value || 0) > 0) return null;  // split manually
    }
    return rowInput(rows[0], "amount");
  }

  function prefillPaymentFromAllocations() {
    var allocated = sumRows("allocations-rows", "amount");
    var withheldInput = document.querySelector('input[name="withheld_amount"]');
    var withheld = Number(withheldInput ? withheldInput.value : 0) || 0;
    if (allocated <= 0) return;
    autofill(firstUntouchedPaymentAmount(),
             round2(Math.max(allocated - withheld, 0)).toFixed(2));
  }

  /* Picking an invoice on a payment with no party yet also fills the
   * customer/supplier box (D74). A party the user already chose is kept. */
  function fillEmptyParty(data) {
    var field = data.customer ? "customer" : (data.supplier ? "supplier" : null);
    if (!field) return;
    var select = document.querySelector('select[name="' + field + '"]');
    if (!select || select.value) return;
    var value = data.customer || data.supplier;
    select.value = value;
    if (select._choices) select._choices.setChoiceByValue(String(value));
  }

  document.addEventListener("change", function (event) {
    var el = event.target;
    if (el.matches && el.matches('select[name$="-item"]')) {
      prefillFromItem(el);
      var row = el.closest("tr");
      if (row) filterBatches(row);
    }
    if (el.matches && el.matches('select[name$="-batch"]')) {
      updateBatchHint(el);
    }
    if (el.matches && el.matches('select[name$="-target"]')) {
      var data = optionData(el, el.value);
      var row = el.closest("tr");
      if (data && row) {
        autofill(rowInput(row, "amount"), data.open || "");
        var withheldInput = document.querySelector('input[name="withheld_amount"]');
        if (withheldInput && data.wht) autofill(withheldInput, data.wht);
        fillEmptyParty(data);
        prefillPaymentFromAllocations();
      }
    }
    /* Blank settlement form: picking the issue jumps to the guided,
     * server-prefilled draft (D71/D74) — one line per item+batch still out. */
    if (el.matches && el.matches('select[name="related_document"]') && el.value) {
      var form = el.closest("form");
      if (form && form.action.indexOf("/new/CONSIGNMENT_SETTLEMENT/") !== -1) {
        window.location.href = "?from=" + encodeURIComponent(el.value);
        return;
      }
    }
    if (el.matches && el.matches('select[name="sale_kind"]') && el.value !== "CASH") {
      clearAutofill(firstUntouchedPaymentAmount());
    }
    recomputeTotals();
  });

  /* ---------- item form: pricing mode toggle (D23) ---------- */

  function initPricingToggle() {
    var mode = document.querySelector('select[name="pricing_mode"]');
    if (!mode) return;
    function wrap(name) {
      var el = document.querySelector('[name="' + name + '"]');
      return el ? el.closest(".field") : null;
    }
    function apply() {
      var auto = mode.value === "AUTO";
      var price = wrap("maintained_price");
      var margin = wrap("auto_margin_pct");
      if (price) price.hidden = auto;
      if (margin) margin.hidden = !auto;
    }
    mode.addEventListener("change", apply);
    apply();
  }

  /* ---------- totals previews (mirror §5; preview only) ---------- */

  function round2(value) {
    return Math.round((value + Number.EPSILON) * 100) / 100;
  }

  function money(value) {
    return value.toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }

  function rowIsDeleted(row) {
    var del = row.querySelector('input[name$="-DELETE"]');
    return del && del.checked;
  }

  function collectParts() {
    var parts = [];
    document.querySelectorAll("#lines-rows tr").forEach(function (row) {
      if (rowIsDeleted(row)) return;
      var qty = Number((rowInput(row, "qty_entered") || {}).value || 0);
      var price = Number((rowInput(row, "unit_price") || {}).value || 0);
      var discount = Number((rowInput(row, "line_discount") || {}).value || 0);
      if (qty <= 0 || price <= 0) return;
      var net = Math.max(round2(qty * price - discount), 0);
      var itemSelect = row.querySelector('select[name$="-item"]');
      var data = itemSelect ? optionData(itemSelect, itemSelect.value) : null;
      var exempt = data ? data.vatExempt === "1" : false;
      parts.push({ value: net, taxable: !exempt });
    });
    document.querySelectorAll("#charges-rows tr").forEach(function (row) {
      if (rowIsDeleted(row)) return;
      var amount = Number((rowInput(row, "amount") || {}).value || 0);
      if (amount <= 0) return;
      var taxableBox = row.querySelector('input[name$="-is_taxable"]');
      parts.push({ value: round2(amount), taxable: !taxableBox || taxableBox.checked });
    });
    return parts;
  }

  function sumRows(tbodyId, suffix) {
    var total = 0;
    document.querySelectorAll("#" + tbodyId + " tr").forEach(function (row) {
      if (rowIsDeleted(row)) return;
      total += Number((rowInput(row, suffix) || {}).value || 0);
    });
    return round2(total);
  }

  function collectSettlementParts() {
    /* Sold quantities × the issue's frozen per-base values (§7.5).
     * Returned/expired quantities earn nothing. Rows sold without a single
     * frozen price (mixed-price issue) are counted so the preview can warn
     * instead of silently undercounting. */
    var parts = [];
    parts.unpriced = 0;
    document.querySelectorAll("#lines-rows tr").forEach(function (row) {
      if (rowIsDeleted(row)) return;
      var soldInput = rowInput(row, "qty_sold");
      if (!soldInput) return;
      var sold = Number(soldInput.value || 0);
      if (sold <= 0) return;
      var perBase = Number(soldInput.dataset.valuePerBase || 0);
      if (perBase <= 0) {
        parts.unpriced += 1;
        return;
      }
      parts.push({
        value: round2(sold * perBase),
        taxable: soldInput.dataset.taxable === "1",
      });
    });
    return parts;
  }

  function collectCostSubtotal() {
    var subtotal = 0;
    document.querySelectorAll("#lines-rows tr").forEach(function (row) {
      if (rowIsDeleted(row)) return;
      var qty = Number((rowInput(row, "qty_entered") || {}).value || 0);
      var cost = Number((rowInput(row, "unit_cost_entered") || {}).value || 0);
      if (qty > 0 && cost > 0) subtotal += round2(qty * cost);
    });
    return round2(subtotal);
  }

  function recomputePaymentCheck(panel) {
    var paid = sumRows("payments-rows", "amount");
    var withheldInput = document.querySelector('input[name="withheld_amount"]');
    var withheld = round2(Number(withheldInput ? withheldInput.value : 0) || 0);
    var allocated = sumRows("allocations-rows", "amount");
    var total = round2(paid + withheld);
    var difference = round2(total - allocated);
    panel.querySelector("[data-out=paid]").textContent = money(paid);
    panel.querySelector("[data-out=withheld]").textContent = money(withheld);
    panel.querySelector("[data-out=grand]").textContent = money(total);
    panel.querySelector("[data-out=allocated]").textContent = money(allocated);
    var diffOut = panel.querySelector("[data-out=difference]");
    diffOut.textContent = money(difference);
    diffOut.classList.toggle("amount-bad", difference !== 0);
    diffOut.classList.toggle("amount-ok", difference === 0 && total > 0);
    var note = panel.querySelector("[data-out=match-note]");
    if (total === 0) note.textContent = "";
    else if (difference === 0) {
      note.textContent = "✓ Fully allocated — ready to post.";
    } else if (difference > 0) {
      note.textContent = "Allocate " + money(difference) + " more to invoices before posting.";
    } else {
      note.textContent = "Allocations exceed the payment by " + money(-difference) + ".";
    }
  }

  function recomputeTotals() {
    var panel = document.getElementById("totals-preview");
    if (!panel) return;
    if (panel.dataset.mode === "payment") {
      recomputePaymentCheck(panel);
      return;
    }
    if (panel.dataset.mode === "cost") {
      var costTotal = collectCostSubtotal();
      panel.querySelector("[data-out=subtotal]").textContent = money(costTotal);
      panel.querySelector("[data-out=discount]").textContent = money(0);
      panel.querySelector("[data-out=tax]").textContent = money(0);
      panel.querySelector("[data-out=grand]").textContent = money(costTotal);
      return;
    }
    var regime = panel.dataset.regime;
    var rate = Number(panel.dataset.rate || 0);
    var whtRate = Number(panel.dataset.whtRate || 0);
    var whtEnabled = panel.dataset.whtEnabled === "1";

    var parts = panel.dataset.mode === "settlement"
      ? collectSettlementParts() : collectParts();
    var subtotal = round2(parts.reduce(function (sum, p) { return sum + p.value; }, 0));
    var docDiscountInput = document.querySelector('input[name="doc_discount"]');
    var docDiscount = Math.min(Number(docDiscountInput ? docDiscountInput.value : 0) || 0, subtotal);

    /* D64 pro-rata: discount spreads across parts by value. */
    var factor = subtotal > 0 ? (subtotal - docDiscount) / subtotal : 0;
    var taxableBase = 0;
    var exemptBase = 0;
    parts.forEach(function (p) {
      if (p.taxable) taxableBase += p.value * factor;
      else exemptBase += p.value * factor;
    });
    taxableBase = round2(taxableBase);
    exemptBase = round2(exemptBase);
    var tax = regime === "VAT" || regime === "TOT" ? round2(taxableBase * rate / 100) : 0;
    var grand = round2(taxableBase + exemptBase + tax);

    /* Cash sale: the payment must equal the total anyway — prefill it. */
    var saleKind = document.querySelector('select[name="sale_kind"]');
    if (saleKind && saleKind.value === "CASH" && grand > 0) {
      autofill(firstUntouchedPaymentAmount(), grand.toFixed(2));
    }

    var whtBox = document.querySelector('input[name="customer_will_withhold"]');
    /* Settlements have no checkbox — they inherit the issue's flag (D70). */
    var willWithhold = whtBox ? whtBox.checked
      : panel.dataset.willWithhold === "1";
    var withholding = whtEnabled && willWithhold
      ? round2(whtRate / 100 * (grand - tax))
      : 0;

    panel.querySelector("[data-out=subtotal]").textContent = money(subtotal);
    panel.querySelector("[data-out=discount]").textContent = money(docDiscount);
    panel.querySelector("[data-out=tax]").textContent = money(tax);
    panel.querySelector("[data-out=grand]").textContent = money(grand);
    var previewNote = panel.querySelector("[data-out=preview-note]");
    if (previewNote) {
      var unpriced = parts.unpriced || 0;
      previewNote.hidden = unpriced === 0;
      if (unpriced > 0) previewNote.textContent = previewNote.dataset.mixedNote;
    }
    var whtRow = panel.querySelector("[data-out=withholding-row]");
    if (whtRow) {
      whtRow.hidden = withholding <= 0;
      panel.querySelector("[data-out=withholding]").textContent = money(withholding);
      var netRow = panel.querySelector("[data-out=net-cash-row]");
      if (netRow) {
        netRow.hidden = withholding <= 0;
        panel.querySelector("[data-out=net-cash]").textContent = money(round2(grand - withholding));
      }
    }
  }

  document.addEventListener("input", function (event) {
    var el = event.target;
    if (!el.closest("#doc-form")) return;
    if (el.name === "grand_total") {
      // Expense & co.: the payment mirrors the entered total
      autofill(firstUntouchedPaymentAmount(),
               (Number(el.value || 0) || 0).toFixed(2));
    }
    if (el.name === "withheld_amount" || el.closest("#allocations-rows")) {
      prefillPaymentFromAllocations();
    }
    recomputeTotals();
  });

  document.addEventListener("DOMContentLoaded", function () {
    enhanceSelects(document);
    initPricingToggle();
    document.querySelectorAll("#lines-rows tr").forEach(filterBatches);
    document.querySelectorAll('select[name$="-batch"]').forEach(updateBatchHint);
    /* Server-prefilled payment drafts (D74): compute the cash line on load */
    prefillPaymentFromAllocations();
    recomputeTotals();
  });
})();
