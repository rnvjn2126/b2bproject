# Accounting architecture

A separate Django app references the existing company workspace. Account codes, group codes and posting keys are workspace scoped. An Indian starter chart is installed on demand and can be extended. The first UI uses an April–March financial year with monthly periods. The posting interface uses accounting dates in India time. Dimensions are workspace-specific branches and cost centres.

Money is accepted as Decimal with at most two fractional digits. Each line is debit or credit, every posted journal has at least two lines and its debit/credit totals agree. A transaction posts the header and lines together. Posting and period lock operations use the same workspace row lock on PostgreSQL. The unique submission key prevents duplicate posting, and replaying the same key with different data is rejected.

Opening balances use one balanced opening journal per workspace. Period reports derive opening, movements and closing amounts from posted lines. Adjustments are separate journals. Corrections reverse the original lines in a new journal in an open period. Only one reversal of an original is allowed. The initial scope uses INR and a single branch and cost centre per journal. Branch-by-branch opening imports and year-end retained earnings carry-forward remain separate work. Period locks are one-way in the initial UI.
