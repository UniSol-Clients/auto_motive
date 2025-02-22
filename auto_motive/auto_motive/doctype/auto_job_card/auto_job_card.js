// Copyright (c) 2025, Khizer and contributors
// For license information, please see license.txt

frappe.ui.form.on('Auto Job Card', {
    refresh(frm) {
        if (!frm.is_new()) {
            frm.add_custom_button(__("Sales Invoice"), function() {
                frappe.model.open_mapped_doc({
                    method: "auto_motive.auto_motive.doctype.auto_job_card.auto_job_card.make_sales_invoice",
                    frm: frm,
                });
            });
        }
    }
});
