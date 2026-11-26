# Accounting security

The initial accounting endpoints are restricted to the workspace owner. Existing sales and manager roles receive no finance access automatically. Owner access is independent of provisional subscription tiers. Requests use Django login, CSRF, and inherited private response headers. Forms restrict foreign keys to the current workspace, and posting revalidates that boundary.

The app has no update or delete routes or admin registration for posted journals. Journal records store the actor and timestamp, and reversal records point to their source. Protect relationships from ordinary deletion. Privileged ORM/raw database changes are outside this application boundary. Before production, require restricted database access, independent tamper evidence, PostgreSQL concurrency verification, least privilege finance permissions and backup/restore tests.
