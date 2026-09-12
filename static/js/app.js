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
        /* D113: "auto" measures space against the scrollable line table and
         * flips the list upward erratically — always open downward. */
        position: "bottom",
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
    applyMonthOnly(body);
    recomputeTotals();
  }

  /* D88: ✕ removes the row it sits in.
   *
   * A row the server has never seen is simply taken out of the page — its
   * inputs stop being submitted, so Django builds a blank form for that
   * index and ignores it. TOTAL_FORMS deliberately stays put: it only
   * says how many forms to build, and leaving it alone keeps every
   * remaining row on the index it was rendered with (renumbering mid-form
   * is how formsets get their wires crossed).
   *
   * A saved row is real data, so we tick the DELETE box Django looks for
   * and hide the row — the deletion lands when the form is saved. */
  function deleteFormsetRow(row) {
    var idInput = row.querySelector('input[name$="-id"]');
    var deleteBox = row.querySelector('input[name$="-DELETE"]');
    if (idInput && idInput.value && deleteBox) {
      deleteBox.checked = true;
      row.hidden = true;
    } else {
      row.remove();
    }
    recomputeTotals();
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-add-row]");
    if (button) addFormsetRow(button.dataset.addRow);
    var remove = event.target.closest("[data-del-row]");
    if (remove) {
      var row = remove.closest("tr");
      if (row) deleteFormsetRow(row);
    }
  });

  /* ---------- confirmation dialog (D93) ----------
   *
   * Any submit button carrying data-confirm explains itself before it fires.
   * The wording lives on the button so each action says what *it* does; a
   * {reason} token is replaced with whatever the linked input holds, so the
   * dialog can read the owner's own words back to them.
   *
   * The click is intercepted rather than the submit, because Correct and
   * Void share one form and differ only by formaction — requestSubmit(button)
   * replays the exact button that was pressed. */

  var confirmed = null;  // the button we have already cleared

  function confirmText(button, key) {
    var raw = button.dataset[key] || "";
    var field = button.dataset.confirmReason;
    var input = field ? document.getElementById(field) : null;
    return raw.replace("{reason}", input ? input.value.trim() : "");
  }

  function fillSlot(dialog, slot, text, tag) {
    var node = dialog.querySelector('[data-confirm-slot="' + slot + '"]');
    if (!node) return;
    node.textContent = "";
    var items = (text || "").split("|").filter(function (line) {
      return line.trim();
    });
    node.hidden = !items.length;
    items.forEach(function (line) {
      var el = document.createElement(tag);
      el.textContent = line.trim();
      node.appendChild(el);
    });
  }

  /* D98: a destructive action must be read, not swatted away. The dialog
   * turns red, itemises every document it is about to reverse, and — when
   * the button asks for it — refuses to arm until the operator types the
   * document number. Reversible actions (Correct) skip all of this. */
  function armTypeGate(dialog, button) {
    var wanted = confirmText(button, "confirmType");
    var gate = dialog.querySelector('[data-confirm-slot="typegate"]');
    var input = dialog.querySelector("[data-confirm-type-input]");
    var ok = dialog.querySelector("[data-confirm-ok]");
    dialog._typeWanted = wanted;
    if (!gate || !input) return;
    input.value = "";
    gate.hidden = !wanted;
    ok.disabled = Boolean(wanted);
    if (!wanted) return;
    var prompt = dialog.querySelector('[data-confirm-slot="typeprompt"]');
    if (prompt) {
      prompt.textContent =
        (button.dataset.confirmTypePrompt || "Type {x} to confirm")
          .replace("{x}", wanted);
    }
  }

  function askToConfirm(button) {
    var dialog = document.getElementById("confirm-dialog");
    if (!dialog || !dialog.showModal) return true;  // no dialog: let it through
    dialog.classList.toggle("confirm-danger", "confirmDanger" in button.dataset);
    dialog.querySelector('[data-confirm-slot="title"]').textContent =
      confirmText(button, "confirmTitle");
    fillSlot(dialog, "body", confirmText(button, "confirmBody"), "p");
    fillSlot(dialog, "list", confirmText(button, "confirmList"), "li");
    fillSlot(dialog, "final", confirmText(button, "confirmFinal"), "span");
    dialog.querySelector("[data-confirm-ok]").textContent =
      confirmText(button, "confirmOk") || "OK";
    armTypeGate(dialog, button);
    dialog._pendingButton = button;
    dialog.showModal();
    return false;
  }

  document.addEventListener("input", function (event) {
    if (!event.target.matches("[data-confirm-type-input]")) return;
    var dialog = document.getElementById("confirm-dialog");
    if (!dialog) return;
    dialog.querySelector("[data-confirm-ok]").disabled =
      event.target.value.trim() !== (dialog._typeWanted || "");
  });

  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-confirm]");
    if (!button || button === confirmed) return;
    var form = button.form;
    /* Let the browser's own "this field is required" run first — we are
     * about to swallow the event that would have triggered it. */
    if (form && !form.reportValidity()) {
      event.preventDefault();
      return;
    }
    event.preventDefault();
    askToConfirm(button);
  }, true);

  document.addEventListener("click", function (event) {
    var dialog = document.getElementById("confirm-dialog");
    if (!dialog) return;
    if (event.target.closest("[data-confirm-cancel]")) {
      dialog.close();
      return;
    }
    if (event.target.closest("[data-confirm-ok]")) {
      if (event.target.closest("[data-confirm-ok]").disabled) return;
      var button = dialog._pendingButton;
      dialog.close();
      if (!button || !button.form) return;
      confirmed = button;              // second pass sails through
      button.form.requestSubmit(button);
      confirmed = null;
    }
  });

  /* ---------- R49: create an item without leaving the document ----------
   *
   * The dialog runs the FULL ItemForm (D67 auto-code, D81 price rules) via
   * fetch. On success the new item is pushed into every item picker on the
   * page — the Choices instance, the pre-enhancement snapshot (_opts), the
   * raw <option> list, and the empty-row template — then selected on the
   * first empty line row (a fresh row is added when none is empty). */

  function newItemOption(data) {
    var option = document.createElement("option");
    option.value = String(data.id);
    option.textContent = data.label;
    option.dataset.price = data.price;
    option.dataset.baseUnit = data.baseUnit;
    option.dataset.vatExempt = data.vatExempt;
    return option;
  }

  function injectItemOption(data) {
    var value = String(data.id);
    document.querySelectorAll('select[name$="-item"]').forEach(function (el) {
      if (el._opts) {
        el._opts.push({ value: value, label: data.label, data: {
          price: data.price, baseUnit: data.baseUnit, vatExempt: data.vatExempt,
        } });
      }
      if (el._choices) {
        el._choices.setChoices([{ value: value, label: data.label }],
                               "value", "label", false);
      } else {
        el.appendChild(newItemOption(data));
      }
    });
    /* Rows added after this point are cloned from the template — it needs
     * the option too, or the new item vanishes from every future row. */
    var template = document.getElementById("lines-empty-row");
    if (template) {
      template.content.querySelectorAll('select[name$="-item"]')
        .forEach(function (el) { el.appendChild(newItemOption(data)); });
    }
  }

  function adoptNewItem(data) {
    injectItemOption(data);
    var target = null;
    document.querySelectorAll("#lines-rows tr").forEach(function (row) {
      if (target || row.hidden) return;
      var select = row.querySelector('select[name$="-item"]');
      if (select && !select.value) target = select;
    });
    if (!target) {
      addFormsetRow("lines");
      var rows = document.querySelectorAll("#lines-rows tr");
      var lastRow = rows[rows.length - 1];
      target = lastRow && lastRow.querySelector('select[name$="-item"]');
    }
    if (!target) return;
    if (target._choices) target._choices.setChoiceByValue(String(data.id));
    target.value = String(data.id);
    target.dispatchEvent(new Event("change", { bubbles: true }));
  }

  document.addEventListener("click", function (event) {
    if (event.target.closest("[data-open-item-modal]")) {
      var dialog = document.getElementById("item-modal");
      if (dialog && dialog.showModal) dialog.showModal();
    }
    if (event.target.closest("[data-item-modal-close]")) {
      var openDialog = document.getElementById("item-modal");
      if (openDialog) openDialog.close();
    }
  });

  /* D142: "Copy from" fills the whole item form from an item already in the
   * catalogue — brand and strength included, which D139's picker deliberately
   * withheld. Clearing one box is easier than remembering which four to fill,
   * and the boxes left unfilled are how the catalogue lost its generics. */

  function copyFromData() {
    var node = document.getElementById("item-copy-data");
    try {
      return node ? JSON.parse(node.textContent) : {};
    } catch (e) {
      return {};
    }
  }

  /* R60: the source may be counted in a unit that is not on the common list,
   * and a select silently keeps its old value when told to take one it has no
   * option for. "Other" is where such a unit belongs. */
  function copyBaseUnit(form, value) {
    var unit = form.querySelector('select[name="base_unit"]');
    var other = form.querySelector('[name="base_unit_other"]');
    if (!unit) return;
    unit.value = value;
    if (unit.value !== value) {
      unit.value = "__other__";
      if (other) other.value = value;
    } else if (other) {
      other.value = "";
    }
    if (unit._choices) unit._choices.setChoiceByValue(unit.value);
    unit.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function applyCopyFrom(button) {
    var form = button.closest("form");
    var source = form && form.querySelector("[data-copy-source]");
    var warning = form && form.querySelector("[data-copy-error]");
    if (!form || !source) return;
    var values = copyFromData()[source.value];
    if (warning) warning.hidden = !!values;
    if (!values) return;
    Object.keys(values).forEach(function (key) {
      if (key === "base_unit") return;
      var input = form.querySelector('[name="' + key + '"]');
      /* Margin boxes are absent for employees (D33) — skip, never invent. */
      if (!input) return;
      if (input.type === "checkbox") input.checked = !!values[key];
      else input.value = values[key];
    });
    /* R59 follows the category until someone touches the box. Copying IS
     * touching it, or the copied exemption would be undone on the next
     * category change. */
    var vat = form.querySelector('input[name="vat_exempt"]');
    if (vat) vat.dataset.touched = "1";
    copyBaseUnit(form, values.base_unit);
    var mode = form.querySelector('select[name="pricing_mode"]');
    if (mode) mode.dispatchEvent(new Event("change", { bubbles: true }));
    /* Land on the brand with it selected: the first thing to change. */
    var name = form.querySelector('[name="name"]');
    if (name) {
      name.focus();
      if (name.select) name.select();
    }
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-copy-from]");
    if (button) applyCopyFrom(button);
  });

  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (form.id !== "item-modal-form") return;
    event.preventDefault();
    var fields = document.getElementById("item-modal-fields");
    fetch(form.action, { method: "POST", body: new FormData(form) })
      .then(function (response) {
        if (response.ok) {
          return response.json().then(function (data) {
            document.getElementById("item-modal").close();
            adoptNewItem(data);
            /* Blank form for the next item; rebind the pricing toggle. */
            return fetch(form.action)
              .then(function (r) { return r.text(); })
              .then(function (html) { fields.innerHTML = html; initItemFormControls(); });
          });
        }
        /* Invalid: the server re-renders the fields with their errors. */
        return response.text().then(function (html) {
          fields.innerHTML = html;
          initItemFormControls();
        });
      });
  });

  /* D146: "Month and year only" swaps the day picker for a month picker on
   * that line alone. The value is carried across both ways, so ticking and
   * unticking never silently empties a box the operator already filled. The
   * server resolves a month to its last day; nothing about the tick is sent or
   * stored. */

  function expiryBox(toggle) {
    var cell = toggle.closest("td") || toggle.parentElement;
    return cell ? cell.querySelector('input[name$="-expiry_entered"]') : null;
  }

  function lastDayOfMonth(year, month) {
    /* Day 0 of the next month is the last day of this one. */
    return new Date(year, month, 0).getDate();
  }

  /* D148: Chrome and Edge have a month picker; Firefox has none and silently
   * renders the input as a plain text box, which is a blank box with no hint
   * and no calendar. Detect it and say what to type, rather than leaving the
   * operator to guess a format. */
  var monthInputSupported = null;

  function supportsMonthInput() {
    if (monthInputSupported === null) {
      var probe = document.createElement("input");
      probe.setAttribute("type", "month");
      monthInputSupported = probe.type === "month";
    }
    return monthInputSupported;
  }

  function toMonthPicker(input) {
    var value = input.value;
    if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
      /* Remember the day, so a mis-tick can be undone without losing it. */
      input.dataset.fullDate = value;
      value = value.slice(0, 7);
    }
    input.type = "month";
    if (!supportsMonthInput()) {
      input.dataset.plainMonth = "1";
      input.placeholder = input.dataset.monthHint || "2026-09";
      input.setAttribute("inputmode", "numeric");
      input.title = input.dataset.monthTitle || "";
    }
    input.value = value;
  }

  function toDayPicker(input) {
    var value = input.value;
    var remembered = input.dataset.fullDate || "";
    input.type = "date";
    if (input.dataset.plainMonth) {
      input.placeholder = "";
      input.removeAttribute("inputmode");
      input.removeAttribute("title");
      delete input.dataset.plainMonth;
    }
    if (!/^\d{4}-\d{2}$/.test(value)) return;
    if (remembered.slice(0, 7) === value) {
      input.value = remembered;
      return;
    }
    var year = parseInt(value.slice(0, 4), 10);
    var month = parseInt(value.slice(5, 7), 10);
    /* Zero-padded, because a date input rejects 2026-09-3. */
    input.value = value + "-" + ("0" + lastDayOfMonth(year, month)).slice(-2);
  }

  document.addEventListener("change", function (event) {
    var toggle = event.target;
    if (!toggle.matches || !toggle.matches("[data-month-only]")) return;
    var input = expiryBox(toggle);
    if (!input) return;
    if (toggle.checked) toMonthPicker(input);
    else toDayPicker(input);
  });

  /* D149: the tick is rendered on for an empty box, but a checked box does not
   * change the input beside it — that is this. */
  function applyMonthOnly(root) {
    (root || document).querySelectorAll("[data-month-only]").forEach(function (toggle) {
      var input = expiryBox(toggle);
      if (input && toggle.checked && input.type !== "month"
          && !input.dataset.plainMonth) {
        toMonthPicker(input);
      }
    });
  }

  /* D128 fills the expiry from the batch that was picked, and that is a full
   * date — the exact stored day, which is the one value a month picker cannot
   * hold. Re-receiving is precisely the case D146 says must not use the tick,
   * so the row unticks itself rather than losing the day. */
  function releaseMonthOnly(row) {
    var toggle = row.querySelector("[data-month-only]");
    if (!toggle || !toggle.checked) return;
    var input = expiryBox(toggle);
    toggle.checked = false;
    if (input) {
      delete input.dataset.fullDate;
      toDayPicker(input);
    }
  }

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

  /* ---------- D128: batch-number suggestions on receiving ----------
   * A batch number is the one master string here that can never be fixed:
   * Batch is unique on (item, batch_no) and four models point at it with
   * PROTECT, so a typo is permanent — the stock sits under a label nobody
   * searches for, and a recall on that batch misses it. Prevention at entry
   * is the only defence there is.
   *
   * Picking an existing batch also fills its expiry, which turns a hard
   * refusal at posting ("already exists with expiry X — you entered Y") into
   * no refusal at all. Matching is case-insensitive because get_or_create is
   * not: `b001` would otherwise become a second batch of the same goods. */

  var BATCH_INDEX = null;

  function batchIndex() {
    if (BATCH_INDEX === null) {
      var node = document.getElementById("batch-index");
      try {
        BATCH_INDEX = node ? JSON.parse(node.textContent) : {};
      } catch (e) {
        BATCH_INDEX = {};
      }
    }
    return BATCH_INDEX;
  }

  function batchSuggestions(row, typed) {
    var itemSelect = row.querySelector('select[name$="-item"]');
    if (!itemSelect || !itemSelect.value) return [];
    var all = batchIndex()[itemSelect.value] || [];
    var needle = (typed || "").trim().toLowerCase();
    if (!needle) return all.slice(0, 5);
    return all.filter(function (b) {
      return b.no.toLowerCase().indexOf(needle) !== -1;
    }).slice(0, 5);
  }

  function applyBatch(row, batch) {
    var input = rowInput(row, "batch_no_entered");
    if (input) input.value = batch.no;
    var expiry = rowInput(row, "expiry_entered");
    if (expiry && batch.expiry) {
      releaseMonthOnly(row);
      expiry.value = batch.expiry;
    }
    renderBatchSuggestions(row);
  }

  function renderBatchSuggestions(row) {
    var input = rowInput(row, "batch_no_entered");
    if (!input) return;
    var cell = input.closest("td");
    if (!cell) return;
    var box = cell.querySelector(".batch-suggest");
    var typed = input.value;
    var matches = batchSuggestions(row, typed);

    /* An exact-but-for-case match is the silent duplicate this exists to
     * stop, so say so rather than just listing it. */
    var clash = null;
    var needle = typed.trim().toLowerCase();
    matches.forEach(function (b) {
      if (needle && b.no.toLowerCase() === needle && b.no !== typed.trim()) clash = b;
    });

    if (!matches.length) {
      if (box) box.remove();
      return;
    }
    if (!box) {
      box = document.createElement("div");
      box.className = "batch-suggest";
      cell.appendChild(box);
    }
    box.innerHTML = "";
    if (clash) {
      var warn = document.createElement("p");
      warn.className = "batch-suggest-warn";
      warn.textContent = "\u201c" + clash.no + "\u201d already exists \u2014 "
        + "a different capitalisation makes a second batch.";
      box.appendChild(warn);
    }
    matches.forEach(function (b) {
      var chip = document.createElement("button");
      chip.type = "button";
      chip.className = "batch-chip";
      chip.textContent = b.no + " \u00b7 "
        + (b.expiry ? "exp " + b.expiry : "no expiry")
        + " \u00b7 " + b.qty + " in stock";
      chip.addEventListener("click", function () { applyBatch(row, b); });
      box.appendChild(chip);
    });
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
    if (el.matches && el.matches('select[name$="-item"]')) {
      var itemRow = el.closest("tr");
      if (itemRow) renderBatchSuggestions(itemRow);
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

  /* R59: drugs are VAT-exempt by law, so the box follows the category —
   * until the user touches it, which always wins. */
  function initVatByCategory() {
    var category = document.querySelector('select[name="category"]');
    var box = document.querySelector('input[name="vat_exempt"]');
    if (!category || !box) return;
    box.addEventListener("click", function () { box.dataset.touched = "1"; });
    category.addEventListener("change", function () {
      if (!box.dataset.touched) box.checked = category.value === "DRUG";
    });
  }

  /* R60: "Other — type it below" reveals the free-text unit box. */
  function initBaseUnitOther() {
    var unit = document.querySelector('select[name="base_unit"]');
    var other = document.querySelector('[name="base_unit_other"]');
    if (!unit || !other) return;
    var wrap = other.closest(".field") || other;
    function apply() { wrap.hidden = unit.value !== "__other__"; }
    unit.addEventListener("change", apply);
    apply();
  }

  function initItemFormControls() {
    initPricingToggle();
    initVatByCategory();
    initBaseUnitOther();
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
    if (el.name && el.name.indexOf("-batch_no_entered") !== -1) {
      var batchRow = el.closest("tr");
      if (batchRow) renderBatchSuggestions(batchRow);
    }
    recomputeTotals();
  });

  /* ---------- D129: number boxes ignore the scroll wheel ----------
   * A focused <input type="number"> changes value on wheel and on arrow keys.
   * The stock-count screen is the dangerous one: it pre-fills every line with
   * the system's own figure and is long enough to force scrolling, so a
   * scroll over a focused box silently rewrites a counted quantity with no
   * trace. Blur on wheel rather than only preventing it, so the page still
   * scrolls normally. */

  document.addEventListener("wheel", function (event) {
    var el = event.target;
    if (el && el.matches && el.matches('input[type="number"]:focus')) {
      el.blur();
    }
  }, { passive: true });

  document.addEventListener("keydown", function (event) {
    if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
    var el = event.target;
    if (el && el.matches && el.matches('input[type="number"]')) {
      event.preventDefault();
    }
  });

  document.addEventListener("DOMContentLoaded", function () {
    enhanceSelects(document);
    applyMonthOnly(document);
    initItemFormControls();
    document.querySelectorAll("#lines-rows tr").forEach(filterBatches);
    document.querySelectorAll('select[name$="-batch"]').forEach(updateBatchHint);
    document.querySelectorAll("#lines-rows tr").forEach(renderBatchSuggestions);
    /* Server-prefilled payment drafts (D74): compute the cash line on load */
    prefillPaymentFromAllocations();
    recomputeTotals();
  });
})();
