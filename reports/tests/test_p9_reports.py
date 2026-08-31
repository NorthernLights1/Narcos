import datetime
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from catalog.models import Account, Customer, ExpenseCategory, Item, Supplier
from core.models import User
from docs.models import Document, DocType, DocumentLine
from docs.posting import post
from money.models import PaymentLine, account_balance
from stock.models import Batch

pytestmark = pytest.mark.django_db

D = Decimal
FAR_EXPIRY = datetime.date(2030, 1, 1)


@pytest.fixture
def owner():
    return User.objects.create_user("boss", password="pw", role=User.Role.OWNER)


@pytest.fixture
def employee():
    return User.objects.create_user("staff", password="pw", role=User.Role.EMPLOYEE)


@pytest.fixture
def cash():
    return Account.objects.create(name="Cash drawer", type=Account.Type.CASH)


@pytest.fixture
def customer():
    return Customer.objects.create(code="C001", name="Selam Pharmacy")


@pytest.fixture
def supplier():
    return Supplier.objects.create(code="S001", name="Addis Pharma")


@pytest.fixture
def drug():
    return Item.objects.create(
        code="AMOX", name="Amoxicillin", base_unit="pack",
        is_batch_tracked=True, has_expiry=True, vat_exempt=True,
        maintained_price=D("15.00"), reorder_level=5,
    )


def _range():
    today = timezone.localdate().isoformat()
    return {"period": "custom", "start": today, "end": today}


def receive(actor, supplier, item, qty=10, cost="10.00", expiry=FAR_EXPIRY):
    doc = Document.objects.create(doc_type=DocType.RECEIVING, created_by=actor,
                                  supplier=supplier)
    DocumentLine.objects.create(
        document=doc, item=item, qty_entered=qty, unit_cost_entered=D(cost),
        batch_no_entered="B-1", expiry_entered=expiry,
        unit_label=item.base_unit,
    )
    return post(doc, actor)


def cash_sale(actor, customer, item, cash, qty=2, price="15.00"):
    doc = Document.objects.create(doc_type=DocType.SALE, created_by=actor,
                                  customer=customer, sale_kind=Document.SaleKind.CASH)
    DocumentLine.objects.create(
        document=doc, item=item, batch=Batch.objects.get(item=item),
        qty_entered=qty, unit_price=D(price), unit_label=item.base_unit,
    )
    PaymentLine.objects.create(document=doc, account=cash, amount=D(price) * qty)
    return post(doc, actor)


def expense(actor, cash, amount="5.00"):
    category = ExpenseCategory.objects.create(name="Rent")
    doc = Document.objects.create(
        doc_type=DocType.EXPENSE, created_by=actor,
        expense_category=category, payee="Landlord", grand_total=D(amount),
    )
    PaymentLine.objects.create(document=doc, account=cash, amount=D(amount))
    return post(doc, actor)


def test_reports_reconcile_to_ledgers_and_export_csv(client, owner, customer,
                                                     supplier, drug, cash):
    client.force_login(owner)
    receive(owner, supplier, drug)
    cash_sale(owner, customer, drug, cash)
    expense(owner, cash)

    assert account_balance(cash) == D("25.00")

    response = client.get(reverse("report_detail", args=["cashbook"]), _range())
    assert response.status_code == 200
    content = response.content.decode()
    assert "Net movement" in content
    assert "25.00" in content

    response = client.get(
        reverse("report_detail", args=["cashbook"]),
        _range() | {"format": "csv"},
    )
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")
    assert "Cash/bank book" not in response.content.decode()


def test_employee_sales_report_hides_cost_and_profit(client, owner, employee,
                                                     customer, supplier, drug, cash):
    receive(owner, supplier, drug)
    cash_sale(owner, customer, drug, cash)

    client.force_login(employee)
    response = client.get(reverse("report_detail", args=["sales"]), _range())
    assert response.status_code == 200
    content = response.content.decode()
    assert "30.00" in content
    assert "COGS" not in content
    assert "Profit" not in content

    response = client.get(reverse("report_detail", args=["profit"]), _range())
    assert response.status_code == 403


def test_owner_profit_report_includes_expenses(client, owner, customer,
                                               supplier, drug, cash):
    client.force_login(owner)
    receive(owner, supplier, drug)
    cash_sale(owner, customer, drug, cash)
    expense(owner, cash)

    response = client.get(reverse("report_detail", args=["profit"]), _range())
    assert response.status_code == 200
    content = response.content.decode()
    assert "Gross profit" in content
    assert "Net profit" in content
    assert "5.00" in content  # 30 revenue - 20 COGS - 5 expense


def test_dashboard_alerts_render(client, owner, customer, supplier, drug):
    receive(owner, supplier, drug, qty=4, expiry=timezone.localdate())
    doc = Document.objects.create(
        doc_type=DocType.SALE, created_by=owner, customer=customer,
        sale_kind=Document.SaleKind.CREDIT,
        due_date=timezone.localdate() - datetime.timedelta(days=1),
    )
    DocumentLine.objects.create(
        document=doc, item=drug, batch=Batch.objects.get(item=drug),
        qty_entered=1, unit_price=D("15.00"), unit_label=drug.base_unit,
    )
    doc = post(doc, owner)

    client.force_login(owner)
    response = client.get(reverse("dashboard"))
    content = response.content.decode()
    assert "Low stock" in content
    assert "AMOX" in content
    assert "AR overdue" in content
    assert doc.doc_no in content


def test_print_hides_cogs_from_employee(client, owner, employee, customer,
                                        supplier, drug, cash):
    receive(owner, supplier, drug)
    sale = cash_sale(owner, customer, drug, cash)

    client.force_login(employee)
    response = client.get(reverse("document_print", args=[sale.pk]), {"layout": "DETAILED"})
    assert response.status_code == 200
    content = response.content.decode()
    assert "Attachment / not a fiscal receipt" in content
    assert "COGS" not in content

    client.force_login(owner)
    response = client.get(reverse("document_print", args=[sale.pk]), {"layout": "DETAILED"})
    assert "COGS" in response.content.decode()


def test_print_renders_ethiopic_party_names(client, owner, supplier, drug, cash):
    customer = Customer.objects.create(
        code="C-ETH",
        name="\u1218\u12f5\u1203\u1292\u1275 \u1264\u1275",
    )
    receive(owner, supplier, drug)
    sale = cash_sale(owner, customer, drug, cash)

    client.force_login(owner)
    response = client.get(reverse("document_print", args=[sale.pk]))
    assert response.status_code == 200
    assert customer.name in response.content.decode()


# --- R75: the report has to agree with the invoice ------------------------

def test_sales_report_revenue_matches_the_invoice(client, owner, customer,
                                                  supplier, drug, cash):
    """Revenue used to be the sum of `line_net`, which carries line discounts
    but neither the delivery charge the customer paid nor the whole-document
    discount they did not — so the report and the invoice disagreed by
    exactly `charges − doc_discount`."""
    from docs.models import DocumentCharge
    from reports.views import _sales_line_rows

    receive(owner, supplier, drug)
    sale = Document.objects.create(doc_type=DocType.SALE, created_by=owner,
                                   customer=customer,
                                   sale_kind=Document.SaleKind.CASH,
                                   doc_discount=D("5.00"))
    DocumentLine.objects.create(
        document=sale, item=drug, batch=Batch.objects.get(item=drug),
        qty_entered=2, unit_price=D("15.00"), unit_label=drug.base_unit,
    )
    DocumentCharge.objects.create(document=sale, label="Delivery",
                                  amount=D("3.00"), is_taxable=False)
    PaymentLine.objects.create(document=sale, account=cash, amount=D("28.00"))
    sale = post(sale, owner)

    today = timezone.localdate()
    _rows, revenue, _cogs = _sales_line_rows(today, today, True)

    assert sale.grand_total == D("28.00")        # 30 lines + 3 delivery - 5
    assert revenue == D("28.00")                 # not 30.00
