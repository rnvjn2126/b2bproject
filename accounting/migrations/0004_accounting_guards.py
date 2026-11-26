from decimal import Decimal

from django.db import migrations


# Validate imported legacy books before applying immutable posting guards.
def seal_existing(apps, schema_editor):
    journal_model = apps.get_model("accounting", "Journal")
    database = schema_editor.connection.alias
    for journal in journal_model.objects.using(database).filter(sealed=False).iterator():
        debits = credits = Decimal(0)
        count = 0
        for side, amount, workspace_id in journal.lines.using(database).values_list(
            "side", "amount", "ledger__workspace_id",
        ):
            if workspace_id != journal.workspace_id or amount <= 0 or side not in ("D", "C"):
                raise RuntimeError(f"Invalid ledger line in legacy journal {journal.pk}.")
            if side == "D":
                debits += amount
            else:
                credits += amount
            count += 1
        if not 2 <= count <= 50 or debits != credits:
            raise RuntimeError(f"Legacy journal {journal.pk} is not balanced.")
        journal_model.objects.using(database).filter(pk=journal.pk).update(sealed=True)


# SQLite may store Decimal values using numeric affinity. Convert each line to integer
# paise before SUM, within the safe integer range for 50 valid journal lines.
BALANCE = """
    SELECT COUNT(*)
    FROM accounting_journalline AS line
    JOIN accounting_ledger AS ledger ON ledger.id = line.ledger_id
    JOIN accounting_accountgroup AS ledger_group ON ledger_group.id = ledger.group_id
    WHERE line.journal_id = NEW.id
    HAVING COUNT(*) BETWEEN 2 AND 50
       AND SUM({paise} * CASE line.side WHEN 'D' THEN 1 ELSE -1 END) = 0
       AND COUNT(*) = COUNT(CASE WHEN ledger.workspace_id = NEW.workspace_id
                       AND ledger_group.workspace_id = NEW.workspace_id THEN 1 END)
"""
PERIOD = """
    SELECT 1 FROM accounting_period AS period
    JOIN accounting_financialyear AS year ON year.id = period.year_id
    WHERE period.id = NEW.period_id AND year.workspace_id = NEW.workspace_id
      AND period.locked_at IS NULL
      AND NEW.date >= period.starts_on AND NEW.date < period.ends_before
"""


def install_guards(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    if vendor == "sqlite":
        balance = BALANCE.replace("{paise}", "CAST(ROUND(line.amount * 100) AS INTEGER)")
        guards = (
            ("accounting_guard_journal_insert", "INSERT", "journal", "NEW.sealed"),
            ("accounting_guard_journal_update", "UPDATE", "journal",
             f"OLD.sealed OR (NEW.sealed AND (NOT EXISTS ({balance}) OR NOT EXISTS ({PERIOD})))"),
            ("accounting_guard_journal_delete", "DELETE", "journal", "OLD.sealed"),
            ("accounting_guard_line_insert", "INSERT", "journalline",
             "(SELECT sealed FROM accounting_journal WHERE id = NEW.journal_id)"),
            ("accounting_guard_line_update", "UPDATE", "journalline",
             "EXISTS (SELECT 1 FROM accounting_journal WHERE id IN (OLD.journal_id, NEW.journal_id) AND sealed)"),
            ("accounting_guard_line_delete", "DELETE", "journalline",
             "(SELECT sealed FROM accounting_journal WHERE id = OLD.journal_id)"),
            ("accounting_guard_period_update", "UPDATE", "period", "OLD.locked_at IS NOT NULL"),
            ("accounting_guard_period_delete", "DELETE", "period", "OLD.locked_at IS NOT NULL"),
        )
        for name, operation, table, condition in guards:
            schema_editor.execute(f"""
                CREATE TRIGGER {name} BEFORE {operation} ON accounting_{table}
                WHEN {condition}
                BEGIN SELECT RAISE(ABORT, 'Invalid change to posted accounting data'); END
            """)
    elif vendor == "postgresql":
        balance = BALANCE.replace("{paise}", "CAST(line.amount * 100 AS BIGINT)")
        schema_editor.execute(f"""
            CREATE FUNCTION accounting_guard_journal() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF TG_OP <> 'INSERT' THEN
                    IF OLD.sealed THEN
                        RAISE EXCEPTION 'Posted journal is immutable' USING ERRCODE = '23514';
                    END IF;
                END IF;
                IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
                IF NEW.sealed THEN
                    IF TG_OP = 'INSERT' OR NOT EXISTS ({balance}) OR NOT EXISTS ({PERIOD}) THEN
                        RAISE EXCEPTION 'Invalid journal posting' USING ERRCODE = '23514';
                    END IF;
                END IF;
                RETURN NEW;
            END;
            $$
        """)
        schema_editor.execute("""
            CREATE FUNCTION accounting_guard_line() RETURNS trigger LANGUAGE plpgsql AS $$
            DECLARE old_id bigint; new_id bigint; parent_sealed boolean;
            BEGIN
                IF TG_OP <> 'INSERT' THEN old_id := OLD.journal_id; END IF;
                IF TG_OP <> 'DELETE' THEN new_id := NEW.journal_id; END IF;
                FOR parent_sealed IN
                    SELECT sealed FROM accounting_journal WHERE id IN (old_id, new_id) ORDER BY id FOR UPDATE
                LOOP
                    IF parent_sealed THEN
                        RAISE EXCEPTION 'Posted journal line is immutable' USING ERRCODE = '23514';
                    END IF;
                END LOOP;
                IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
                RETURN NEW;
            END;
            $$
        """)
        schema_editor.execute("""
            CREATE FUNCTION accounting_guard_period() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF OLD.locked_at IS NOT NULL THEN
                    RAISE EXCEPTION 'Closed period is immutable' USING ERRCODE = '23514';
                END IF;
                IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
                RETURN NEW;
            END;
            $$
        """)
        for name, table, events in (
            ("journal", "journal", "INSERT OR UPDATE OR DELETE"),
            ("line", "journalline", "INSERT OR UPDATE OR DELETE"),
            ("period", "period", "UPDATE OR DELETE"),
        ):
            schema_editor.execute(f"""
                CREATE TRIGGER accounting_guard_{name} BEFORE {events} ON accounting_{table}
                FOR EACH ROW EXECUTE FUNCTION accounting_guard_{name}()
            """)
    else:
        raise RuntimeError("Accounting guards require SQLite or PostgreSQL.")


def remove_guards(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    if vendor == "sqlite":
        for name, operations in (
            ("journal", ("insert", "update", "delete")), ("line", ("insert", "update", "delete")),
            ("period", ("update", "delete")),
        ):
            for operation in operations:
                schema_editor.execute(f"DROP TRIGGER accounting_guard_{name}_{operation}")
    elif vendor == "postgresql":
        for name, table in (("journal", "journal"), ("line", "journalline"), ("period", "period")):
            schema_editor.execute(f"DROP TRIGGER accounting_guard_{name} ON accounting_{table}")
            schema_editor.execute(f"DROP FUNCTION accounting_guard_{name}()")


class Migration(migrations.Migration):
    dependencies = [("accounting", "0003_journal_sealed")]
    operations = [
        migrations.RunPython(seal_existing, migrations.RunPython.noop),
        migrations.RunPython(install_guards, remove_guards),
    ]
