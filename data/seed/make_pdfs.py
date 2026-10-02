"""Regenerate the seed invoices in data/seed/invoices/.

PDFs are written uncompressed with one Tj per line so invoice_tool can pull the
text back out with a regex (no PDF dep is on the approved list).
Run: python data/seed/make_pdfs.py
"""

import pathlib

HERE = pathlib.Path(__file__).parent
OUT = HERE / "invoices"


def pdf(lines: list[str]) -> bytes:
    esc = lambda s: s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")  # noqa: E731
    body = ["BT", "/F1 11 Tf", "72 720 Td", "16 TL"] + [f"({esc(l)}) Tj T*" for l in lines]
    content = ("\n".join(body) + "\nET\n").encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"endstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode() + b"0000000000 65535 f \n"
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


DOCS = {
    # Company X latest: the one the demo must find.
    "INV-X-2024-0912-acme.pdf": [
        "ACME SUPPLY CO.  (company: Company X)",
        "INVOICE",
        "Invoice Number: CX-2024-0912",
        "Invoice Date: 2024-09-12",
        "Due Date: 2024-10-12",
        "",
        "Description                 Qty     Unit      Amount",
        "Steel bracket kit            40    48.00     1920.00",
        "Calibration service           2   950.00     1900.00",
        "Freight                       1     1000.00   1000.00",
        "",
        "Subtotal                              4820.00",
        "Amount Due: USD 4,820.00",
        "Payment Terms: Net 30",
        "Thank you for your business.",
    ],
    # Same company, older: must lose the "latest" comparison.
    "INV-X-2024-0703-acme.pdf": [
        "ACME SUPPLY CO.  (company: Company X)",
        "INVOICE",
        "Invoice Number: CX-2024-0703",
        "Invoice Date: 2024-07-03",
        "Due Date: 2024-08-02",
        "",
        "Description                 Qty     Unit      Amount",
        "Steel bracket kit            10    48.00      480.00",
        "",
        "Subtotal                              480.00",
        "Amount Due: USD 480.00",
        "Payment Terms: Net 30",
    ],
    # Wrong company: must be filtered out before parsing.
    "INV-Y-2024-0805-other.txt": [
        "GLOBEX TRADING  (company: Company Y)",
        "INVOICE",
        "Invoice Number: GY-2024-0805",
        "Invoice Date: 2024-08-05",
        "Due Date: 2024-09-04",
        "",
        "Consulting retainer          1    9999.99     9999.99",
        "",
        "Amount Due: USD 9,999.99",
    ],
}

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name, lines in DOCS.items():
        p = OUT / name
        p.write_bytes(pdf(lines) if p.suffix == ".pdf" else ("\n".join(lines) + "\n").encode())
        print(f"wrote {p.name} ({p.stat().st_size} bytes)")
