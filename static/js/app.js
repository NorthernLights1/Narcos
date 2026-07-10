/* Narcos UI enhancements: dynamic formset rows, searchable selects, and a
 * client-side totals preview. Display convenience only — the server's tax
 * engine (docs/tax.py) remains the single authority for stored totals (D32). */

(function () {
  "use strict";

  /* ---------- searchable selects (Choices.js, vendored) ---------- */

  function enhanceSelects(root) {
    if (typeof Choices === "undefined") return;
    root.querySelectorAll("select[data-search]").forEach(function (el) {
      if (el.dataset.enhanced) return;
      el.dataset.enhanced = "1";
      new Choices(el, {
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

  /* ---------- prefill from the picked item ---------- */

  function selectedOption(select) {
    return select.options[select.selectedIndex] || null;
  }

  function rowInput(row, suffix) {
    return row.querySelector('[name$="-' + suffix + '"]');
  }

  function prefillFromItem(select) {
    var row = select.closest("tr");
    var option = selectedOption(select);
    if (!row || !option) return;
    var price = rowInput(row, "unit_price");
    if (price && (!price.value || Number(price.value) === 0) && option.dataset.price) {
      price.value = option.dataset.price;
    }
    var unitLabel = rowInput(row, "unit_label");
    if (unitLabel && !unitLabel.value && option.dataset.baseUnit) {
      unitLabel.value = option.dataset.baseUnit;
    }
  }

  document.addEventListener("change", function (event) {
    var el = event.target;
    if (el.matches && el.matches('select[name$="-item"]')) prefillFromItem(el);
    recomputeTotals();
  });

  /* ---------- totals preview (mirrors §5; preview only) ---------- */

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
      var option = itemSelect ? selectedOption(itemSelect) : null;
      var exempt = option ? option.dataset.vatExempt === "1" : false;
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

  function sumRows(tbodyId, suffix) {
    var total = 0;
    document.querySelectorAll("#" + tbodyId + " tr").forEach(function (row) {
      if (rowIsDeleted(row)) return;
      total += Number((rowInput(row, suffix) || {}).value || 0);
    });
    return round2(total);
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

    var parts = collectParts();
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

    var whtBox = document.querySelector('input[name="customer_will_withhold"]');
    var withholding = whtEnabled && whtBox && whtBox.checked
      ? round2(whtRate / 100 * (grand - tax))
      : 0;

    panel.querySelector("[data-out=subtotal]").textContent = money(subtotal);
    panel.querySelector("[data-out=discount]").textContent = money(docDiscount);
    panel.querySelector("[data-out=tax]").textContent = money(tax);
    panel.querySelector("[data-out=grand]").textContent = money(grand);
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
    if (event.target.closest("#doc-form")) recomputeTotals();
  });

  document.addEventListener("DOMContentLoaded", function () {
    enhanceSelects(document);
    recomputeTotals();
  });
})();
