# bill_interpreter/ocr_hidroelectrica.py
from pprint import pprint

import pdfplumber
import re
import pandas as pd
from collections import OrderedDict
import json

### UTILITY FUNCTIONS

def split_numeric_unit(text):
    if not text:
        return text, ""
    pattern = re.compile(r"([-\d\.,]+)\s*(.*)", flags=re.UNICODE)
    m = pattern.match(text.strip())
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return text, ""

def clean_field(text):
    if not text:
        return ""
    cleaned = re.sub(r"_+", "", text, flags=re.UNICODE)
    cleaned = re.sub(r'[_,]+$', '', cleaned, flags=re.UNICODE)
    return cleaned.strip()

def _clean_cell(x):
    if x is None:
        return ""
    return re.sub(r"\s+", " ", str(x)).strip()

def _clean_header_row(row):
    if not row:
        return row
    return [_clean_cell(c) for c in row]

def extract_text_from_page(page):
    try:
        return page.extract_text() or ""
    except Exception as e:
        print(f"Error extracting text: {e}")
        return ""

def extract_tables_from_page(page):
    try:
        return page.extract_tables() or []
    except Exception as e:
        print(f"Error extracting tables from page: {e}")
        return []

def extract_ordered_fields_once(text, field_patterns):
    results = {}
    current_pos = 0
    for key, pat in field_patterns.items():
        matches = [(m.start(1), m.end(1), m.group(1).strip())
                   for m in re.finditer(pat, text, flags=re.IGNORECASE|re.UNICODE)]
        valid_match = None
        for start, end, value in matches:
            if start >= current_pos:
                valid_match = (start, end, value)
                break
        if valid_match is None and matches:
            valid_match = matches[0]
        if valid_match is not None:
            results[key] = valid_match[2]
            current_pos = valid_match[0] + 1
        else:
            results[key] = None
    return results

### PARSING FUNCTIONS

def parse_page1(page):
    text = extract_text_from_page(page)
    general = {}
    header_match = re.search(
        r"Factur[ăa]\s+fiscal[ăa]\s+seria\s+(\S+)\s+nr\.\s*([0-9]+)\s+din\s+data\s+de\s+([\d]{2}[./-][\d]{2}[./-][\d]{2,4})",
        text, flags=re.IGNORECASE|re.UNICODE)
    if header_match:
        general["serie"] = header_match.group(1).strip()
        general["numar_factura"] = header_match.group(2).strip()
        general["data"] = header_match.group(3).strip()

    supplier_match = re.search(r"Furnizor\s*(.*?)\n(?:\s*\n|CIF:)",
                               text, flags=re.DOTALL|re.IGNORECASE|re.UNICODE)
    general["furnizor"] = clean_field(supplier_match.group(1)) if supplier_match else None

    call_center_match = re.search(r"CALL\s*Center\s*(.*?)\n",
                                  text, flags=re.DOTALL|re.IGNORECASE|re.UNICODE)
    general["call_center"] = clean_field(call_center_match.group(1)) if call_center_match else None

    correspondence_match = re.search(
        r"Adres[ăa]\s+de\s+coresponden[tț][ăa]\s*(.*?)\n",
        text, flags=re.DOTALL|re.IGNORECASE|re.UNICODE)
    general["correspondence_address"] = clean_field(correspondence_match.group(1)) if correspondence_match else None

    client_match = re.search(r"Client\s*:\s*(.*?)\n",
                             text, flags=re.DOTALL|re.IGNORECASE|re.UNICODE)
    general["client"] = clean_field(client_match.group(1)) if client_match else None
    return general

def parse_produse_table(page):
    tables = extract_tables_from_page(page)
    for table in tables:
        if not table:
            continue
        table[0] = _clean_header_row(table[0])
        if any("produse" in (cell or "").lower() for cell in table[0]):
            return table
    return None

def parse_detailed_info(page):
    text = extract_text_from_page(page)
    field_patterns = OrderedDict([
        ("adresa_de_consum", r"Adres[ăa]\s+loc\s+de\s+consum\s*(.*?)\n"),
        ("cod_loc_consum",   r"Cod\s+loc\s+consum\s*[:\-]?\s*(\d+)"),
        ("POD",              r"(?:\bPOD\b)\s*[:\-]?\s*([0-9,]+)")
    ])
    results = extract_ordered_fields_once(text, field_patterns)
    return results

def parse_servicii_facturate_table(page):
    page_text = (extract_text_from_page(page) or "").lower()
    if ("servicii" not in page_text) or ("facturate" not in page_text):
        return None

    tables = extract_tables_from_page(page)

    for table in tables:
        if not table or not table[0]:
            continue
        table[0] = _clean_header_row(table[0])   # <<< normalize header (kills \n)
        header = " | ".join([(c or "").lower() for c in table[0]])
        if ("servicii" in header or "denumire" in header) and (
            "cantitate" in header or "valoare" in header or "pret" in header or "preț" in header
        ):
            return table

    for table in tables:
        if table and table[0]:
            table[0] = _clean_header_row(table[0])
            if any("servicii facturate" in (cell or "").lower() for cell in table[0]):
                return table
    return None

def merge_tables(tables):
    merged_rows = []
    header = None
    for table in tables:
        if not table or len(table) == 0:
            continue
        table[0] = _clean_header_row(table[0])  # <<< normalize header
        if header is None and is_valid_header(table[0]):
            header = table[0]
            merged_rows.extend(table[1:])
        else:
            if header is not None and len(table[0]) == len(header):
                if is_valid_header(table[0]):
                    merged_rows.extend(table[1:])
                else:
                    merged_rows.extend(table)
            else:
                continue
    return [header] + merged_rows if header else merged_rows

def is_valid_header(row):
    keywords = ["nr crt", "cantitate", "valoare", "index", "masurări", "masurari", "serie contor", "perioad"]
    for cell in row:
        if cell and any(kw in cell.lower() for kw in keywords):
            return True
    return False

def extract_period_from_text(text):
    if text:
        text = text.replace("\n", " ")
    dates = re.findall(r"(\d{2}[./-]\d{2}[./-]\d{2,4})", text, flags=re.UNICODE)
    if len(dates) >= 2:
        return dates[0].strip(), dates[1].strip()
    return None, None

def process_servicii_periods(table):
    if not table or len(table) < 1:
        return table
    header = _clean_header_row(table[0])  # <<< ensure clean
    table[0] = header
    col_index = None
    for i, col in enumerate(header):
        if col and "denumire servicii facturate" in col.lower():
            col_index = i
            break
    if col_index is None:
        return table
    new_header = header[:col_index] + ["denumire servicii", "perioadă start", "perioadă incheiere", "comentarii"] + header[col_index+1:]
    new_table = [new_header]
    pattern = re.compile(r"^(.*?)\s*(\d{2}[./-]\d{2}[./-]\d{2,4})\s*[-–]\s*(\d{2}[./-]\d{2}[./-]\d{2,4})(.*)$", flags=re.UNICODE)
    for row in table[1:]:
        cell_text = row[col_index] if col_index < len(row) else ""
        cell_text = cell_text.replace("\n", " ")
        match = pattern.match(cell_text.strip())
        if match:
            serviciu = match.group(1).strip()
            perioada_start = match.group(2).strip()
            perioada_incheiere = match.group(3).strip()
            comentarii = match.group(4).strip()
        else:
            serviciu = cell_text.strip()
            perioada_start = ""
            perioada_incheiere = ""
            comentarii = ""
        new_row = row[:col_index] + [serviciu, perioada_start, perioada_incheiere, comentarii] + row[col_index+1:]
        new_table.append(new_row)
    return new_table

def parse_masurari_tables(pages):
    candidate_tables = []
    start_found = False
    for page in pages:
        text = extract_text_from_page(page)
        if not start_found:
            if "detalii m" in text.lower():
                start_found = True
                tables = extract_tables_from_page(page)
                for table in tables:
                    if table and any("serie contor" in (cell or "").lower() for cell in table[0]):
                        table[0] = _clean_header_row(table[0])  # <<< normalize header
                        candidate_tables.append(table)
        else:
            tables = extract_tables_from_page(page)
            for table in tables:
                if table and table[0]:
                    table[0] = _clean_header_row(table[0])  # <<< normalize header
                candidate_tables.append(table)
    if not candidate_tables:
        return None
    merged_table = merge_tables(candidate_tables)
    if not merged_table or len(merged_table) < 2:
        return None
    # Inline period splitting for "perioadă facturare" column:
    header = _clean_header_row(merged_table[0])  # <<< ensure clean
    merged_table[0] = header
    col_index = None
    for i, col in enumerate(header):
        if col and "perioad" in col.lower():
            col_index = i
            break
    if col_index is not None:
        new_header = header[:col_index] + ["masurări perioadă start", "masurări perioadă final"] + header[col_index+1:]
        new_rows = [new_header]
        period_pattern = re.compile(r"(\d{2}[./-]\d{2}[./-]\d{2,4})", flags=re.UNICODE)
        for row in merged_table[1:]:
            cell_text = row[col_index] if col_index < len(row) else ""
            cell_text = cell_text.replace("\n", " ")
            dates = period_pattern.findall(cell_text)
            if len(dates) >= 2:
                start_date = dates[0].strip()
                end_date = dates[1].strip()
            else:
                start_date = ""
                end_date = ""
            new_row = row[:col_index] + [start_date, end_date] + row[col_index+1:]
            new_rows.append(new_row)
        merged_table = new_rows
    # Inline processing for columns with both "index" and "stabilire":
    header = _clean_header_row(merged_table[0])  # <<< ensure clean
    new_header = []
    columns_to_split = []
    for idx, col in enumerate(header):
        if col and ("index" in col.lower() and "stabilire" in col.lower()):
            if "vechi" in col.lower():
                new_header.extend(["Index vechi", "Mod stabilire vechi"])
            elif "nou" in col.lower():
                new_header.extend(["Index nou", "Mod stabilire nou"])
            else:
                new_header.extend(["Index", "Mod stabilire"])
            columns_to_split.append(idx)
        else:
            new_header.append(col)
    new_rows = [new_header]
    for row in merged_table[1:]:
        new_row = []
        for i in range(len(row)):
            if i in columns_to_split:
                cell_text = row[i].replace("\n", " ").strip() if row[i] else ""
                tokens = cell_text.split()
                if tokens:
                    index_val = tokens[0]
                    mod_stabilire = " ".join(tokens[1:]) if len(tokens) > 1 else ""
                else:
                    index_val, mod_stabilire = "", ""
                new_row.extend([index_val, mod_stabilire])
            else:
                new_row.append(row[i])
        new_rows.append(new_row)
    merged_table = new_rows
    return merged_table

def merge_continuation_rows(table):
    if not table:
        return table
    merged = []
    header = [cell.replace("\n", " ") if cell else "" for cell in table[0]]
    merged.append(header)
    for row in table[1:]:
        new_row = [cell.replace("\n", " ") if cell else "" for cell in row]
        if new_row[0].strip() == "":
            last_row = merged[-1]
            for i, cell in enumerate(new_row):
                if cell.strip():
                    if i < len(last_row) and last_row[i]:
                        last_row[i] = last_row[i] + " " + cell.strip()
                    elif i < len(last_row):
                        last_row[i] = cell.strip()
                    else:
                        last_row.append(cell.strip())
        else:
            merged.append(new_row)
    return merged

def build_invoice(pdf_path):
    invoice = {}
    with pdfplumber.open(pdf_path) as pdf:
        pages = pdf.pages
        if not pages:
            return invoice
        invoice["general"] = parse_page1(pages[0])
        produse_table = parse_produse_table(pages[0])
        if produse_table:
            produse_table[0] = _clean_header_row(produse_table[0])  # <<< normalize header
            invoice["produse"] = produse_table
        detailed_info = []
        servicii_facturate_tables = []
        for page in pages[1:]:
            detailed = parse_detailed_info(page)
            if detailed:
                detailed_info.append(detailed)
            sf_table = parse_servicii_facturate_table(page)
            if sf_table:
                sf_table[0] = _clean_header_row(sf_table[0])  # <<< normalize header
                servicii_facturate_tables.append(sf_table)
        invoice["detailed"] = detailed_info
        if servicii_facturate_tables:
            merged_sf = merge_tables(servicii_facturate_tables)
            merged_sf = process_servicii_periods(merged_sf)
            merged_sf[0] = _clean_header_row(merged_sf[0])  # <<< normalize header
            invoice["servicii_facturate"] = merged_sf
        masurari = parse_masurari_tables(pages)
        if masurari:
            masurari[0] = _clean_header_row(masurari[0])  # <<< normalize header
            invoice["masurari"] = masurari
    return invoice

def export_invoice_to_excel(invoice, output_prefix="invoice"):
    if "general" in invoice:
        df_general = pd.DataFrame([invoice["general"]])
        df_general.to_excel(f"{output_prefix}_general.xlsx", index=False)
    if "produse" in invoice:
        produse = invoice["produse"]
        if len(produse) > 1:
            merged_produse = merge_continuation_rows(produse)
            df_produse = pd.DataFrame(merged_produse[1:], columns=merged_produse[0])
            df_produse.to_excel(f"{output_prefix}_produse.xlsx", index=False)
    if "servicii_facturate" in invoice:
        sf = invoice["servicii_facturate"]
        if sf and len(sf) > 1:
            merged_sf = merge_continuation_rows(sf)
            df_sf = pd.DataFrame(merged_sf[1:], columns=merged_sf[0])
            df_sf.to_excel(f"{output_prefix}_servicii_facturate.xlsx", index=False)
    if "masurari" in invoice:
        masurari = invoice["masurari"]
        if masurari and len(masurari) > 1:
            merged_masurari = merge_continuation_rows(masurari)
            df_masurari = pd.DataFrame(merged_masurari[1:], columns=merged_masurari[0])
            df_masurari.to_excel(f"{output_prefix}_masurari.xlsx", index=False)
    if "detailed" in invoice and invoice["detailed"]:
        df_detailed = pd.DataFrame(invoice["detailed"])
        df_detailed.to_excel(f"{output_prefix}_detailed.xlsx", index=False)

if __name__ == '__main__':
    pdf_path = "FX-24103693423.PDF"
    invoice_data = build_invoice(pdf_path)
    print("Extracted Invoice Data:")
    pprint(invoice_data)
    export_invoice_to_excel(invoice_data, output_prefix="invoice_output")
