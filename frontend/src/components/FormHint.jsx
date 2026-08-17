import { HelpCircle } from "lucide-react";

const FORM_HINTS = {
  "MGT-7": "Annual return (Section 92) — file within 60 days of AGM. Contains directors, shareholders and other prescribed particulars.",
  "MGT-1": "Register of Members maintained under Section 88(1)(a).",
  "AOC-4": "Financial statements (Section 137) — file adopted financials within 30 days of AGM.",
  "DIR-3 KYC": "Annual director KYC (Section 153) — mandatory by 30 September for every DIN holder as on 31 March.",
  "ADT-1": "Auditor appointment intimation (Section 139) — file within 15 days of appointment.",
  "DPT-3": "Return of deposits and outstanding money not treated as deposits — annually by 30 June.",
  "MSME-1": "Half-yearly return of outstanding MSME payments beyond 45 days (Section 405).",
  "AGM": "Annual General Meeting under Section 96 — hold by 30 September of the following FY.",
  "BM": "Board meeting under Section 173 — at least four per year with a max gap of 120 days.",
  "CSR-2": "CSR reporting under Section 135 — filed as an addendum to AOC-4.",
  "MBP-1": "Directors' disclosure of interest under Section 184 — at the first board meeting of the FY.",
  "MBP-4": "Register of Contracts and Arrangements with related parties (Section 189).",
  "IEPF-2": "Statement of unclaimed and unpaid amounts under Section 125 — within 60 days of AGM.",
  "CHG-7": "Register of Charges (Section 85).",
  "PAS-3": "Return of allotment of shares (Section 39).",
  "DIR-12": "Particulars of appointment/change of directors (Section 152).",
  "INC-22": "Notice of situation / change of registered office (Section 12).",
};

export default function FormHint({ code, className = "" }) {
  const hint = FORM_HINTS[code];
  if (!hint) return null;
  return (
    <span className={`form-hint ${className}`} data-testid={`hint-${code}`} title={hint}>
      <HelpCircle size={11} />
    </span>
  );
}

export { FORM_HINTS };
