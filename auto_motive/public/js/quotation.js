frappe.ui.form.on('Quotation', {
    refresh(frm) {
        if (!frm.is_new()) {
            frm.add_custom_button(__('Create Job Card'), function () {
                frappe.call({
                    method: "frappe.client.insert",
                    args: {
                        doc: Object.assign({}, frm.doc, { 
                            doctype: "Auto Job Card", 
                            name: undefined,
                            docstatus:0,
                            status: "Created"
                        })
                    },
                    callback: function (response) {
                        if (response.message) {
                            frappe.msgprint(__('Auto Job Card Created Successfully'));
                            frappe.set_route("auto-job-card", response.message.name);
                        }
                    }
                });
            });
        }
    }
});
