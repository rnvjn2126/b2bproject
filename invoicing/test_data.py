from datetime import date
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model

from accounting.models import AccountGroup, Ledger
from accounting.services import setup_books
from dashboard.models import BusinessAccount, Customer, Quote, QuoteLine, RFQ, RFQLine, Supplier, SupplierOffer
from orders.models import OrderMovement, PurchaseOrder, SalesOrder, SalesOrderLine

from .models import CompanyGSTRegistration, TaxRate
from .services import prepare_draft


class InvoiceFixture:
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.owner = users.create_user(username="draft-owner")
        cls.other = users.create_user(username="draft-other")
        cls.workspace = BusinessAccount.objects.create(owner=cls.owner, name="Synthetic drafts")
        cls.other_workspace = BusinessAccount.objects.create(owner=cls.other, name="Other draft workspace")
        cls.registration = CompanyGSTRegistration.objects.create(
            workspace=cls.workspace, gstin="27AAAAA0000A1Z0", registered_name="Synthetic Company",
            registered_address="Synthetic Company Address",
        )
        cls.rate = TaxRate.objects.create(
            workspace=cls.workspace, item_kind="goods", item_code="000000", effective_from=date(2026, 4, 1),
            source_url="https://example.test/synthetic-only", integrated_rate="12", central_rate="6", local_rate="6",
        )
        buyer = Customer.objects.create(owner=cls.owner, name="Synthetic Customer")
        supplier = Supplier.objects.create(owner=cls.owner, name="Synthetic Supplier", address="Synthetic Mill Address")
        day = date(2026, 5, 1)
        rfq = RFQ.objects.create(owner=cls.owner, customer=buyer, received_on=day)
        item = RFQLine.objects.create(owner=cls.owner, rfq=rfq, description="Synthetic steel", quantity="10", unit="kg")
        offer = SupplierOffer.objects.create(owner=cls.owner, rfq_line=item, supplier=supplier, available_quantity="10",
                                             unit_price="80", unit="kg", delivery_days=3)
        quote = Quote.objects.create(owner=cls.owner, rfq=rfq, number="SYN-1", target_margin_percent="20",
                                     minimum_margin_percent="10", maximum_discount_percent="5")
        quote_line = QuoteLine.objects.create(owner=cls.owner, quote=quote, rfq_line=item, supplier_offer=offer,
                                              quantity="10", unit="kg", selling_price_per_unit="100",
                                              landed_cost_per_unit="80", discount_percent="0")
        cls.order = SalesOrder.objects.create(
            workspace=cls.workspace, source_quote=quote, quotation_number=quote.number, quotation_revision=1,
            customer=buyer, customer_name=buyer.name, customer_address="Synthetic Customer Address",
            created_by=cls.owner, status=SalesOrder.Status.APPROVED,
        )
        sales_line = SalesOrderLine.objects.create(order=cls.order, quote_line=quote_line, description=item.description,
                                                   quantity="10", unit="kg", unit_price="100")
        purchase = PurchaseOrder.objects.create(
            requirement=sales_line, offer=offer, supplier=supplier, supplier_name=supplier.name, quantity="10",
            unit_price="80", delivery_on=day, submission_key=uuid4(), created_by=cls.owner, status=SalesOrder.Status.APPROVED,
        )
        cls.receipt = OrderMovement.objects.create(purchase_order=purchase, quantity="5", date=day, reference="SYN-R1",
                                                   recorded_by=cls.owner)
        cls.dispatch = OrderMovement.objects.create(sales_line=sales_line, quantity="3", date=day, reference="SYN-D1",
                                                    recorded_by=cls.owner)

    def draft(self, movement, workspace=None, actor=None, **overrides):
        args = {
            "movement_id": movement.pk, "registration_id": self.registration.pk, "party_gstin": "24BBBBB0000B1Z0",
            "item_code": "000000", "place_of_supply": "27", "local_component": "sgst", "inclusive": False,
            "discount": Decimal(0), "freight": Decimal(0), "round_off": Decimal(0),
        }
        return prepare_draft(workspace or self.workspace, actor or self.owner, **(args | overrides))

    def issue_inputs(self, draft):
        year = setup_books(self.workspace, self.owner, 2026)
        duties = AccountGroup.objects.get(workspace=self.workspace, name="Duties and taxes")
        cgst, sgst = [Ledger.objects.get_or_create(workspace=self.workspace, code=code,
                                                 defaults={"name": code, "group": duties})[0]
                      for code in ("OUT-CGST", "OUT-SGST")]
        ledger_ids = dict(Ledger.objects.filter(workspace=self.workspace, code__in=("1100", "4000")).values_list(
            "code", "pk",
        ))
        return year, {
            "draft_id": draft.pk, "posting_on": draft.supply_on, "confirmed_total": draft.total,
            "ledger_ids": {"receivable": ledger_ids["1100"], "sales": ledger_ids["4000"],
                           "output_cgst": cgst.pk, "output_sgst": sgst.pk},
        }

    def purchase_issue_inputs(self, draft):
        setup_books(self.workspace, self.owner, 2026)
        ledger_ids = dict(Ledger.objects.filter(workspace=self.workspace, code__in=("2000", "1300", "5000")).values_list(
            "code", "pk",
        ))
        return {
            "draft_id": draft.pk, "posting_on": draft.supply_on, "confirmed_total": draft.total,
            "supplier_invoice_date": draft.supply_on, "supplier_reference": "inv/11",
            "recoverable_input_tax": True,
            "ledger_ids": {"payable": ledger_ids["2000"], "purchases": ledger_ids["5000"], "input_igst": ledger_ids["1300"]},
        }
