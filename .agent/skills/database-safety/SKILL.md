# Skill: Database Safety

Before DB mutation:
1. identify exact instance/database/schema/table
2. inspect current schema
3. inspect relevant counts/constraints
4. verify migration state
5. create/verify required backup
6. define rollback
7. re-check target
8. apply only authorized operation
9. verify schema/data/runtime afterward

STOP on drift or ambiguous target.
