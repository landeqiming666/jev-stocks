from .extract import normalize_text

TITLE_MAX_CHARS = 120
ITEM_NAMES = {
    "1.01": "Entry into a Material Definitive Agreement",
    "1.02": "Termination of a Material Definitive Agreement",
    "2.01": "Completion of Acquisition or Disposition of Assets",
    "2.02": "Results of Operations and Financial Condition",
    "2.03": "Creation of a Direct Financial Obligation",
    "3.01": "Notice of Delisting or Failure to Satisfy a Listing Rule",
    "3.02": "Unregistered Sales of Equity Securities",
    "4.01": "Changes in Registrant's Certifying Accountant",
    "4.02": "Non-Reliance on Previously Issued Financial Statements",
    "5.01": "Changes in Control of Registrant",
    "5.02": "Departure or Election of Directors or Officers",
    "5.03": "Amendments to Articles of Incorporation or Bylaws",
    "5.07": "Submission of Matters to a Vote of Security Holders",
    "7.01": "Regulation FD Disclosure",
    "8.01": "Other Events",
    "9.01": "Financial Statements and Exhibits",
}


def build_title(
    *,
    form_type: str,
    items: str | None,
    primary_doc_description: str | None,
    first_line: str | None,
) -> str:
    if form_type in {"8-K", "8-K/A"}:
        names = [
            ITEM_NAMES.get(item.strip(), "Item " + item.strip())
            for item in (items or "").split(",")
            if item.strip()
        ]
        prefix, body = "8-K: ", "；".join(names) or primary_doc_description or ""
    else:
        prefix, body = "6-K: ", first_line or primary_doc_description or ""
    body = next((line for line in normalize_text(body).splitlines() if line.strip()), "")
    return (prefix + body)[:TITLE_MAX_CHARS]
