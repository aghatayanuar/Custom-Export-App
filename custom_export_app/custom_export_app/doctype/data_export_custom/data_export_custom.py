# Copyright (c) 2025, DAS and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now
from custom_export_app.custom_export_app.doctype.data_export_custom.exporter_new import Exporter

class DataExportCustom(Document):
	
    def autoname(self):
        if not getattr(self, "reference_doctype", None):
            self.name = f"DataExport-{now().replace(':', '-').replace(' ', '_').replace('.', '-')}"
        else:
            safe_doctype = self.reference_doctype.replace(" ", "_")
            timestamp = now()
            safe_ts = timestamp.replace(":", "-").replace(" ", "_").replace(".", "-")
            self.name = f"{safe_doctype}_Export_on_{safe_ts}"

def test():
    doctype = "Purchase Receipt"

    docname = "Purchase_Receipt_Export_on_2025-12-03_15-48-48-705981"

    export_fields = {
        "Purchase Receipt": ["name","company","supplier"],
        "items": ["name","item_code", "qty"]
    }

    # export_fields = {
    #         "Purchase Receipt": [
    #             "name",
    #             "supplier",
    #             "naming_series",
    #             "posting_date",
    #             "posting_time",
    #             "company",
    #             "currency",
    #             "conversion_rate",
    #             "status",
    #             "base_net_total"
    #         ],
    #         "items": [
    #             "name",
    #             "received_qty",
    #             "item_code",
    #             "item_name"
    #         ]
    #     }

    export_filters = {
        # "status": "Pending"
    }

    export_records = "5_records"  # bisa "all", "by_filter", "blank_template"

    file_type = "CSV"

    e = Exporter(
        doctype,
        docname,
        export_fields=export_fields,
        export_data=export_records != "blank_template",
        export_filters=export_filters,
        file_type=file_type,
        export_page_length=5 if export_records == "5_records" else None,
    )

    e.build_response()

@frappe.whitelist()
def export_data(
    docname=None,
    doctype=None,
    export_fields=None,
    export_filters=None,
    export_records="by_filter",
    file_type="CSV"
):
    try:
        export_fields = frappe.parse_json(export_fields or "{}")
        export_filters = frappe.parse_json(export_filters or "[]")

        mapped_fields = {}
        parent_doctype = doctype

        for dt, fields in export_fields.items():
            if not fields:
                continue  

            child_table_fieldname = None
            for df in frappe.get_meta(parent_doctype).fields:
                if df.fieldtype == "Table" and df.options == dt:
                    child_table_fieldname = df.fieldname
                    break

            key = child_table_fieldname or dt  
            
            if "name" not in fields:
                fields.insert(0, "name")  

            mapped_fields[key] = fields

        # frappe.msgprint(f"Mapped Fields:\n{mapped_fields}")

        frappe.enqueue(
            do_export_background,
            queue="long",
            job_name=f"Export {doctype} for {docname}",
            timeout=3000,
            docname=docname,
            doctype=doctype,
            export_fields=mapped_fields,
            export_filters=export_filters,
            export_records=export_records,
            file_type=file_type
        )

    except Exception as e:
        if docname:
            frappe.db.set_value("Data Export Custom", docname, "status", "Failed")
            frappe.db.commit()
        frappe.log_error(message=str(e), title="Export enqueue failed")
        return {"status": "failed", "error": str(e)}

    return {"status": "queued"}



def do_export_background(
		docname,
        doctype,
        export_fields,
        export_filters,
        export_records,
        file_type
	):

	frappe.db.set_value("Data Export Custom", docname, "status", "Processing")

	frappe.db.commit()

	e = Exporter(
        doctype,
        docname,
        export_fields=export_fields,
        export_data=export_records != "blank_template",
        export_filters=export_filters,
        file_type=file_type,
        export_page_length=5 if export_records == "5_records" else None,
    )

	e.build_response()

	frappe.db.set_value("Data Export Custom", docname, "status", "Completed")


@frappe.whitelist()
def get_running_export_job(docname=None):
    from rq.registry import StartedJobRegistry
    from frappe.utils.background_jobs import get_queues
    from datetime import datetime

    queues = get_queues()
    q_long = next((q for q in queues if "long" in q.name), None)
    if not q_long:
        return None

    registry = StartedJobRegistry(queue=q_long)
    running_jobs = []

    for job_id in registry.get_job_ids():
        job = q_long.fetch_job(job_id)
        if not job:
            continue

        job_name = job.kwargs.get("job_name", "") or job.description or ""
        job_kwargs = job.kwargs.get("kwargs", {})
        method = job.kwargs.get("method", "")

        if "do_export_background" not in str(method):
            continue

        if docname and docname not in job_name:
            continue

        started_at = job.started_at
        elapsed_seconds = 0
        if started_at:
            now = datetime.utcnow()
            elapsed_seconds = int((now - started_at).total_seconds())

        running_jobs.append({
            "job_id": job.id,
            "job_name": job_name,
            "elapsed_seconds": elapsed_seconds,
            "docname": job_kwargs.get("docname"),
            "doctype": job_kwargs.get("doctype"),
            "file_type": job_kwargs.get("file_type"),
        })

    return running_jobs[0] if running_jobs else None
