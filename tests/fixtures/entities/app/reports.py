"""Raw-SQL reporting: references only table names (drives inferred access)."""


def invoice_totals(conn):
    return conn.execute("SELECT number, amount FROM invoices")
