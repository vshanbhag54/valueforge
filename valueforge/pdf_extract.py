from __future__ import annotations

import fitz

KEYWORDS=("balance sheet","statement of profit","profit and loss","cash flow","cash flows",
          "auditor","related party","contingent liability","borrowings","promoter",
          "management discussion","notes to accounts","impairment","revenue from operations")

def extract_relevant_pdf_text(pdf_bytes: bytes, max_chars: int = 26000) -> str:
    doc=fitz.open(stream=pdf_bytes,filetype="pdf")
    selected=[]
    for number,page in enumerate(doc, start=1):
        text=page.get_text("text")
        low=text.lower()
        if number<=4 or any(k in low for k in KEYWORDS):
            if text.strip():
                selected.append(f"\n[PDF page {number}]\n{text}")
        if sum(len(x) for x in selected)>=max_chars: break
    doc.close()
    joined="\n".join(selected)
    return joined[:max_chars]
