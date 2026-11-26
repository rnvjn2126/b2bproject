from django.db import migrations


VALID_ISSUE = """
    SELECT 1
      FROM invoicing_invoicedraft d
      JOIN accounting_journal j ON j.id = NEW.journal_id
      JOIN accounting_period p ON p.id = j.period_id
      JOIN accounting_financialyear y ON y.id = p.year_id
      JOIN dashboard_businessaccount w ON w.id = NEW.workspace_id
     WHERE d.id = NEW.draft_id AND d.kind = 'sales'
       AND d.workspace_id = NEW.workspace_id
       AND j.workspace_id = NEW.workspace_id AND y.workspace_id = NEW.workspace_id
       AND y.id = NEW.year_id AND j.sealed AND j.kind = 'sale_invoice'
       AND p.locked_at IS NULL AND d.supply_on = NEW.posting_on AND j.date = NEW.posting_on
       AND j.submitted_by_id = NEW.issued_by_id AND w.owner_id = NEW.issued_by_id
       AND d.total = NEW.total AND j.reference = NEW.number
       AND NEW.number = ('INT-SI-' || CAST(y.start_year AS varchar) || '-' || CAST(NEW.sequence AS varchar))
"""


def install_guards(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    if vendor == "sqlite":
        schema_editor.execute(f"""
            CREATE TRIGGER invoicing_validate_issue BEFORE INSERT ON invoicing_issuedinvoice
            WHEN NOT EXISTS ({VALID_ISSUE})
            BEGIN
                SELECT RAISE(ABORT, 'Invalid issued invoice journal link');
            END
        """)
        for operation in ("update", "delete"):
            schema_editor.execute(f"""
                CREATE TRIGGER invoicing_immutable_issue_{operation}
                BEFORE {operation.upper()} ON invoicing_issuedinvoice
                BEGIN
                    SELECT RAISE(ABORT, 'Issued invoice is immutable');
                END
            """)
    elif vendor == "postgresql":
        schema_editor.execute(f"""
            CREATE FUNCTION invoicing_guard_issued_invoice() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF TG_OP <> 'INSERT' THEN
                    RAISE EXCEPTION 'Issued invoice is immutable' USING ERRCODE = '23514';
                END IF;
                IF NOT EXISTS ({VALID_ISSUE}) THEN
                    RAISE EXCEPTION 'Invalid issued invoice journal link' USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END;
            $$
        """)
        schema_editor.execute("""
            CREATE TRIGGER invoicing_guard_issued_invoice
            BEFORE INSERT OR UPDATE OR DELETE ON invoicing_issuedinvoice
            FOR EACH ROW EXECUTE FUNCTION invoicing_guard_issued_invoice()
        """)
    else:
        raise RuntimeError("Invoice guards require SQLite or PostgreSQL.")


def remove_guards(apps, schema_editor):
    if schema_editor.connection.vendor == "sqlite":
        for trigger in ("invoicing_validate_issue", "invoicing_immutable_issue_update", "invoicing_immutable_issue_delete"):
            schema_editor.execute(f"DROP TRIGGER {trigger}")
    elif schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("DROP TRIGGER invoicing_guard_issued_invoice ON invoicing_issuedinvoice")
        schema_editor.execute("DROP FUNCTION invoicing_guard_issued_invoice()")


class Migration(migrations.Migration):
    dependencies = [("invoicing", "0003_issuedinvoice")]
    operations = [migrations.RunPython(install_guards, remove_guards)]
