# Why the CBE account shows a negative balance

**Investigated 2026-09-13** against the restored client database
(snapshot 2026-09-08 07:13). All queries read-only. No client data was changed.

---

## The answer in one sentence

Nothing is broken and no money is missing: the system was never told how much
was in the CBE account on the day they started using it, so it has been
counting down from zero.

---

## The numbers

As at **2026-09-07** (the last full day in the snapshot):

| | |
|---|---|
| CBE balance shown | **−889,737.00** |
| BOA balance shown | +30,600.00 |
| Money into CBE since go-live | 2,710,516.00 |
| Money out of CBE since go-live | −3,600,253.00 |
| Go-live (earliest posted document) | **2026-07-22**, GRN-000001 |

The first CBE transaction ever recorded — PV-000001 on 2026-07-23, a supplier
payment of 27,888.00 — took the account negative on day one, and it never
recovered. That is the fingerprint of a missing opening balance. An account
that genuinely ran dry would show a positive period first.

## The ledger is correct — it reconciles to the cent

| Check | Figure |
|---|---|
| Goods received from suppliers | 6,052,343.00 (117 documents) |
| Paid to suppliers | 3,591,753.00 (62 documents) |
| **Still owed to suppliers (AP ledger)** | **2,460,590.00** = exactly the difference |
| Goods sold to customers | 4,817,556.00 (175 documents) |
| Received from customers | 2,732,616.00 (78 documents) |
| **Still owed by customers (AR ledger)** | **2,084,940.00** = exactly the difference |

Every supplier payment is fully allocated against an invoice that exists in the
system — **0.00 unallocated**. So they are not paying off old pre-system debts
through the system either.

The CBE outflow (3,600,253) is the 3,591,753 of supplier payments plus one
8,500.00 reversal: receipt RC-000002 was posted twice on 2026-08-01 and voided
with the reason *"duplicated"*. The system reversed it correctly. That is the
only correction in 143 rows.

## The cause

At go-live the client entered **42 opening stock documents** — so they did do an
opening exercise, and kept doing it as late as 2026-09-02. But:

| Opening document | Entered |
|---|---|
| Opening stock | 42 |
| **Opening cash** | **0** |
| **Opening receivable** | **0** |
| **Opening payable** | **0** |

The opening exercise covered stock and stopped. The bank accounts therefore
started at 0.00 in the system while holding real money at the bank.

Since go-live they have genuinely paid out 889,737.00 more through CBE than they
have taken in through it. That figure is correct. It is simply being subtracted
from zero instead of from their real 2026-07-22 bank balance.

The payments were allowed through because `negative_balance_policy` is **ALLOW**
— "goes through and the account shows red on the Finance page". The on-screen
help for that very setting says the usual cause is an opening balance that was
never entered. That is exactly what happened.

---

## What to say to the client

Plain words, no jargon:

> The red figure on the CBE account is not money you have lost, and it is not a
> mistake in the system. When we started in July we told the program what stock
> you had, but we never told it how much money was already sitting in the CBE
> account that morning. So it began counting from zero.
>
> Since July you have paid suppliers about 889,737 Birr more through CBE than
> customers have paid into it. That part is correct and normal — you have been
> buying stock faster than you have been collecting. The program has simply been
> subtracting it from zero instead of from your real starting balance.
>
> To fix it I need one number from you: **what the CBE account balance was on
> the morning of 22 July 2026.** Your CBE statement or passbook for that date
> will show it. Once I enter that one figure, the account will show your true
> balance and the red will go away by itself.

Two things worth adding if they ask:

- **Is any money missing?** No. Every payment is matched to a supplier invoice
  in the system — nothing is unaccounted for. One duplicate receipt on 1 August
  was already caught and cancelled.
- **Will this change what customers owe me?** No. The customer and supplier
  balances are separate and already correct: customers owe 2,084,940 and they
  owe suppliers 2,460,590.

---

## What to do

**No code change. No data surgery. One document, entered through the app.**

1. Get the CBE statement balance as at the **morning of 2026-07-22** (and the
   BOA balance for the same date — BOA has the same gap, it just happens to
   still be positive).
2. On the client's machine, log in **as the owner** (opening balances are
   owner-only), go to **Transactions → Opening cash**.
3. Set the document date to **2026-07-22** and add one line per account:
   CBE = the statement figure, BOA = the statement figure. Amounts must be
   positive.
4. In the notes, write where the figures came from — e.g. *"CBE statement
   22/07/2026, BOA passbook same date"* — so the next person can check it.
5. Post it. The Finance page will recompute; no rebuild or restart is needed.

`books_closed_through` is currently **None**, so back-dating to 22 July is
allowed and nothing needs unlocking first.

**Do not** try to fix this by editing rows or by entering a balancing payment.
Ledgers are append-only and a fake payment would corrupt the supplier position.
Opening cash is the built-in, correct instrument and it already works.

### Expected result

New CBE balance = (statement balance on 2026-07-22) − 889,737. If the real
opening balance was above ~890,000 the account turns positive immediately. If it
was below that, the account is genuinely overdrawn and that is a real business
conversation, not a software one.

---

## Caveats — read before quoting any figure

- **These numbers are from the 2026-09-08 snapshot.** The client's live machine
  has run for five more days. Re-derive on their machine before telling them a
  figure; the queries are cheap.
- **This development copy contains two rows that are not client data** — they
  were entered here after the snapshot: PV-000063 (−450,000.00, 2026-09-11) and
  RC-000083 (+15,300.00, 2026-09-12). They are excluded from every figure above.
  The app currently shows −1,324,437.00 here because it includes them; the real
  client figure at snapshot is **−889,737.00**.
- **The same gap exists for receivables and payables.** No opening AR or AP was
  ever entered, so any customer who owed money before 2026-07-22, or any
  supplier they owed before that date, is invisible to the system. Worth raising
  as a separate question — it is a bigger conversation than the bank balance and
  should not be bundled into this fix.

## Is there a product change to make?

Optional, and not required to fix this client. The system let them complete an
opening exercise for stock while silently leaving cash, AR and AP at zero. A
go-live checklist — or a dismissible banner on the Finance page reading *"No
opening cash has been entered; bank balances start from zero"* — would have
caught this in July. Worth a decision entry if it is taken up; it should not be
built on the strength of one incident.
