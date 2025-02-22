# Copyright (c) 2025, Khizer and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, nowdate
from frappe.model.mapper import get_mapped_doc

class AutoJobCard(Document):
    pass
@frappe.whitelist()
def make_sales_invoice(source_name: str, target_doc=None):
	if not frappe.db.get_singles_value(
		"Selling Settings", "allow_sales_order_creation_for_expired_quotation"
	):
		auto_jc = frappe.db.get_value(
			"Auto Job Card", source_name, ["transaction_date", "valid_till"], as_dict=1
		)
		if auto_jc.valid_till and (
			auto_jc.valid_till < auto_jc.transaction_date or auto_jc.valid_till < getdate(nowdate())
		):
			frappe.throw(_("Validity period of this auto job card has ended."))

	return _make_sales_invoice(source_name, target_doc)


def _make_sales_invoice(source_name, target_doc=None, ignore_permissions=False):
	customer = _make_customer(source_name, ignore_permissions)
	ordered_items = frappe._dict(
		frappe.db.get_all(
			"Quotation Item",
			{"docstatus": 1, "parent": source_name},
			["item_code", "sum(qty)"],
			group_by="item_code",
			as_list=1,
		)
	)

	selected_rows = [x.get("name") for x in frappe.flags.get("args", {}).get("selected_items", [])]

	def set_missing_values(source, target):
		if customer:
			target.customer = customer.name
			target.customer_name = customer.customer_name

			# sales team
			if not target.get("sales_team"):
				for d in customer.get("sales_team") or []:
					target.append(
						"sales_team",
						{
							"sales_person": d.sales_person,
							"allocated_percentage": d.allocated_percentage or None,
							"commission_rate": d.commission_rate,
						},
					)

		if source.referral_sales_partner:
			target.sales_partner = source.referral_sales_partner
			target.commission_rate = frappe.get_value(
				"Sales Partner", source.referral_sales_partner, "commission_rate"
			)

		target.flags.ignore_permissions = ignore_permissions
		target.run_method("set_missing_values")
		target.run_method("calculate_taxes_and_totals")

	def update_item(obj, target, source_parent):
		balance_qty = obj.qty - ordered_items.get(obj.item_code, 0.0)
		target.qty = balance_qty if balance_qty > 0 else 0
		target.stock_qty = flt(target.qty) * flt(obj.conversion_factor)

		if obj.against_blanket_order:
			target.against_blanket_order = obj.against_blanket_order
			target.blanket_order = obj.blanket_order
			target.blanket_order_rate = obj.blanket_order_rate

	def can_map_row(item) -> bool:
		"""
		Row mapping from Quotation to Sales order:
		1. If no selections, map all non-alternative rows (that sum up to the grand total)
		2. If selections: Is Alternative Item/Has Alternative Item: Map if selected and adequate qty
		3. If selections: Simple row: Map if adequate qty
		"""
		balance_qty = item.qty - ordered_items.get(item.item_code, 0.0)
		if balance_qty <= 0:
			return False

		has_qty = balance_qty

		if not selected_rows:
			return not item.is_alternative

		if selected_rows and (item.is_alternative or item.has_alternative_item):
			return (item.name in selected_rows) and has_qty

		# Simple row
		return has_qty

	doclist = get_mapped_doc(
		"Auto Job Card",
		source_name,
		{
			"Auto Job Card": {"doctype": "Sales Invoice"},
			"Quotation Item": {
				"doctype": "Sales Invoice Item",
				"field_map": {"parent": "prevdoc_docname", "name": "quotation_item"},
				"postprocess": update_item,
				"condition": can_map_row,
			},
			"Sales Taxes and Charges": {"doctype": "Sales Taxes and Charges", "reset_value": True},
			"Sales Team": {"doctype": "Sales Team", "add_if_empty": True},
			"Payment Schedule": {"doctype": "Payment Schedule", "add_if_empty": True},
		},
		target_doc,
		set_missing_values,
		ignore_permissions=ignore_permissions,
	)

	return doclist

def _make_customer(source_name, ignore_permissions=False):
	quotation = frappe.db.get_value(
		"Auto Job Card",
		source_name,
		["order_type", "quotation_to", "party_name", "customer_name"],
		as_dict=1,
	)

	if quotation.quotation_to == "Customer":
		return frappe.get_doc("Customer", quotation.party_name)

	# Check if a Customer already exists for the Lead or Prospect.
	existing_customer = None
	if quotation.quotation_to == "Lead":
		existing_customer = frappe.db.get_value("Customer", {"lead_name": quotation.party_name})
	elif quotation.quotation_to == "Prospect":
		existing_customer = frappe.db.get_value("Customer", {"prospect_name": quotation.party_name})

	if existing_customer:
		return frappe.get_doc("Customer", existing_customer)

	# If no Customer exists, create a new Customer or Prospect.
	if quotation.quotation_to == "Lead":
		return create_customer_from_lead(quotation.party_name, ignore_permissions=ignore_permissions)
	elif quotation.quotation_to == "Prospect":
		return create_customer_from_prospect(quotation.party_name, ignore_permissions=ignore_permissions)

	return None

def create_customer_from_lead(lead_name, ignore_permissions=False):
	from erpnext.crm.doctype.lead.lead import _make_customer

	customer = _make_customer(lead_name, ignore_permissions=ignore_permissions)
	customer.flags.ignore_permissions = ignore_permissions

	try:
		customer.insert()
		return customer
	except frappe.MandatoryError as e:
		handle_mandatory_error(e, customer, lead_name)
  
def create_customer_from_prospect(prospect_name, ignore_permissions=False):
	from erpnext.crm.doctype.prospect.prospect import make_customer as make_customer_from_prospect

	customer = make_customer_from_prospect(prospect_name)
	customer.flags.ignore_permissions = ignore_permissions

	try:
		customer.insert()
		return customer
	except frappe.MandatoryError as e:
		handle_mandatory_error(e, customer, prospect_name)
  
def handle_mandatory_error(e, customer, lead_name):
	from frappe.utils import get_link_to_form

	mandatory_fields = e.args[0].split(":")[1].split(",")
	mandatory_fields = [_(customer.meta.get_label(field.strip())) for field in mandatory_fields]

	frappe.local.message_log = []
	message = _("Could not auto create Customer due to the following missing mandatory field(s):") + "<br>"
	message += "<br><ul><li>" + "</li><li>".join(mandatory_fields) + "</li></ul>"
	message += _("Please create Customer from Lead {0}.").format(get_link_to_form("Lead", lead_name))

	frappe.throw(message, title=_("Mandatory Missing"))
