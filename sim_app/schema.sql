CREATE TABLE IF NOT EXISTS invoices (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  idempotency_key TEXT NOT NULL UNIQUE,
  vendor        TEXT NOT NULL,
  company       TEXT NOT NULL,
  invoice_number TEXT,
  amount        TEXT NOT NULL,          -- decimal string, no float rounding
  currency      TEXT NOT NULL DEFAULT 'USD',
  due_date      TEXT,
  source_file   TEXT,
  created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_invoices_company ON invoices(company);
CREATE INDEX IF NOT EXISTS idx_invoices_created ON invoices(created_at);
