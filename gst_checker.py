import openai
import pdfplumber
import os
from dotenv import load_dotenv
import pandas as pd
import requests
from fpdf import FPDF
import pytesseract
from pdf2image import convert_from_path
from PyPDF2 import PdfReader
import tempfile
import json
import ast
import re
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# Set the tesseract executable path (update if your path is different)
# pytesseract.pytesseract.tesseract_cmd = r"C:\Users\vimal\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"

# Remove detect_invoice_type and use a single prompt for all invoices

def extract_text_from_pdf(file):
    # Try extracting text normally
    reader = PdfReader(file)
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
    if text.strip():
        return text

    # If no text found, use OCR
    file.seek(0)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        tmp_file.write(file.read())
        tmp_file_path = tmp_file.name

    images = convert_from_path(tmp_file_path)
    ocr_text = ""
    for img in images:
        ocr_text += pytesseract.image_to_string(img)
    return ocr_text

def get_invoice_feedback(invoice_text, use_mock=False):
    if use_mock:
        return (
            "✅ GSTIN: Valid format found\n"
            "✅ HSN Code: Present for all items\n"
            "❌ CGST/SGST mismatch detected\n"
            "✅ Total matches subtotal + taxes\n"
            "⚠️ Invoice Date is missing\n"
            "✅ Signature section is present"
        )

    prompt = f'''
You are an invoice validation assistant. From the provided invoice text, return a JSON with the following fields:
{{
  "Invoice_Basic_Details": {{ ... }},
  "Vendor_Details": {{ ... }},
  "Tax_Verification": {{ ... }},
  "Compliance_Check": {{ ... }},
  "Critical_Issues": [],
  "Warnings": [],
  "Summary": "A short, clear summary of the invoice status and any issues (1-2 sentences, no extra explanation).",
  "Verdict": "Ready to process" or "Not ready to process"
}}
Set "Verdict" to "Ready to process" ONLY if there are NO Critical_Issues and NO Warnings. If there are ANY Critical_Issues or Warnings, set "Verdict" to "Not ready to process". Only output the JSON. Do not add any explanation or extra text.

Invoice content:
{invoice_text}
'''

    response = openai.ChatCompletion.create(
        model="gpt-4-1106-preview",
        messages=[
            { "role": "system", "content": "You are a GST invoice checker bot." },
            { "role": "user", "content": prompt }
        ],
        temperature=0.2,
        max_tokens=800
    )

    return response.choices[0].message['content']

def extract_fields_3way(invoice_text, po_text, grn_text):
    """
    Use LLM to extract structured fields from invoice, PO, and GRN text.
    Returns a dict: { 'invoice': {...}, 'po': {...}, 'grn': {...} }
    """
    prompt = f'''
You are an expert document parser. Extract the following fields from each document and return a JSON with this structure:
{{
  "invoice": {{
    "invoice_number": str,
    "vendor_name": str,
    "invoice_date": str,
    "po_number": str,
    "items": [{{"name": str, "quantity": float, "unit_price": float, "tax_percent": float, "total_price": float}}],
    "gstin": str
  }},
  "po": {{
    "po_number": str,
    "buyer_name": str,
    "vendor_name": str,
    "po_date": str,
    "items": [{{"name": str, "quantity": float, "unit_price": float, "total_price": float}}]
  }},
  "grn": {{
    "grn_number": str,
    "po_number": str,
    "delivery_date": str,
    "items": [{{"name": str, "quantity": float}}],
    "delivery_status": str
  }}
}}
Only output the JSON. Do not add any explanation or extra text.
---
Invoice Text:
{invoice_text}
---
PO Text:
{po_text}
---
GRN Text:
{grn_text}
'''
    response = openai.ChatCompletion.create(
        model="gpt-4-1106-preview",
        messages=[
            { "role": "system", "content": "You are an expert document parser." },
            { "role": "user", "content": prompt }
        ],
        temperature=0.2,
        max_tokens=1200
    )
    import json, ast, re
    raw = response.choices[0].message['content']
    match = re.search(r'(\{[\s\S]*\})', raw)
    json_str = match.group(1) if match else raw
    try:
        return json.loads(json_str)
    except Exception:
        try:
            return ast.literal_eval(json_str)
        except Exception:
            return None

def validate_3way_fields(fields):
    """
    Perform all matching/validation logic on extracted fields.
    Returns: { 'verdict': ..., 'error': ... }
    """
    import re
    if not fields or not isinstance(fields, dict):
        return {"verdict": "Not ready to process", "error": "Could not extract fields from documents."}
    invoice = fields.get('invoice', {})
    po = fields.get('po', {})
    grn = fields.get('grn', {})
    # 1. PO number match
    if not (invoice.get('po_number') == po.get('po_number') == grn.get('po_number')):
        return {"verdict": "Not ready to process", "error": "PO number does not match across documents."}
    # 2. Vendor name match
    if invoice.get('vendor_name','').strip().lower() != po.get('vendor_name','').strip().lower():
        return {"verdict": "Not ready to process", "error": "Vendor name does not match between Invoice and PO."}
    # 3. GSTIN format
    gstin = invoice.get('gstin','')
    if not re.match(r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$', gstin):
        return {"verdict": "Not ready to process", "error": "GSTIN is missing or incorrectly formatted in Invoice."}
    # 4. Item names, quantities, unit prices match (Invoice vs PO)
    invoice_items = {i['name'].strip().lower(): i for i in invoice.get('items',[])}
    po_items = {i['name'].strip().lower(): i for i in po.get('items',[])}
    for name, inv_item in invoice_items.items():
        po_item = po_items.get(name)
        if not po_item:
            return {"verdict": "Not ready to process", "error": f"Item '{name}' in Invoice not found in PO."}
        if float(inv_item.get('quantity',0)) != float(po_item.get('quantity',0)):
            return {"verdict": "Not ready to process", "error": f"Quantity mismatch for item '{name}' between Invoice and PO."}
        if float(inv_item.get('unit_price',0)) != float(po_item.get('unit_price',0)):
            return {"verdict": "Not ready to process", "error": f"Unit price mismatch for item '{name}' between Invoice and PO."}
    # 5. GRN–PO: received items in GRN must match quantity in PO
    grn_items = {i['name'].strip().lower(): i for i in grn.get('items',[])}
    for name, po_item in po_items.items():
        grn_item = grn_items.get(name)
        if not grn_item:
            return {"verdict": "Not ready to process", "error": f"Item '{name}' in PO not found in GRN."}
        if float(grn_item.get('quantity',0)) != float(po_item.get('quantity',0)):
            return {"verdict": "Not ready to process", "error": f"Quantity mismatch for item '{name}' between GRN and PO."}
    # 6. GRN–Invoice: Invoice quantities must not exceed received quantities in GRN
    for name, inv_item in invoice_items.items():
        grn_item = grn_items.get(name)
        if not grn_item:
            return {"verdict": "Not ready to process", "error": f"Item '{name}' in Invoice not found in GRN."}
        if float(inv_item.get('quantity',0)) > float(grn_item.get('quantity',0)):
            return {"verdict": "Not ready to process", "error": f"Invoice quantity for item '{name}' exceeds GRN received quantity."}
    # 7. No extra items in Invoice not delivered per GRN
    for name in invoice_items:
        if name not in grn_items:
            return {"verdict": "Not ready to process", "error": f"Extra item '{name}' in Invoice not delivered per GRN."}
    # 8. Delivery date >= PO date
    from datetime import datetime
    try:
        po_date = datetime.strptime(po.get('po_date',''), '%Y-%m-%d')
        delivery_date = datetime.strptime(grn.get('delivery_date',''), '%Y-%m-%d')
        if delivery_date < po_date:
            return {"verdict": "Not ready to process", "error": "Delivery date in GRN is before PO date."}
    except Exception:
        pass  # Ignore date check if parsing fails
    # All checks passed
    return {"verdict": "Ready to process", "error": None}

def validate_3way(invoice_text, po_text, grn_text, use_mock=False):
    if use_mock:
        return {
            "verdict": "Not ready to process",
            "error": "Vendor name mismatch between Invoice and PO."
        }
    fields = extract_fields_3way(invoice_text, po_text, grn_text)
    return validate_3way_fields(fields)

def extract_text_from_excel(file):
    try:
        df = pd.read_excel(file)

        if df.empty:
            return "⚠️ Excel file is empty."

        # Convert rows to readable text
        text = "GST Invoice Details from Excel:\n"
        for i, row in df.iterrows():
            row_text = ", ".join([f"{col}: {row[col]}" for col in df.columns if not pd.isna(row[col])])
            text += f"Invoice {i + 1}: {row_text}\n\n"

        return text
    except Exception as e:
        return f"⚠️ Failed to read Excel file: {str(e)}"

def generate_pdf_report(feedback, filename="gst_feedback.pdf"):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    pdf.multi_cell(0, 10, feedback)
    output_path = os.path.join("generated_reports", filename)
    os.makedirs("generated_reports", exist_ok=True)
    pdf.output(output_path)

    return output_path


