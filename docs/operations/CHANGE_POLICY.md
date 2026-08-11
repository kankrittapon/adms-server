# AI-Brain Change Policy

## Modes

`READ-ONLY`: inspect/report only. `LIMITED WRITE`: only the exact
authorized target/change. `MAINTENANCE WRITE`: broader scope only when
explicitly defined.

## Hard stops

STOP before writing if the host/service/database is ambiguous, a secret
would be exposed, live state materially differs, an unrelated service
would be affected, required rollback is unavailable, or destructive
authorization is not explicit.

## Post-write gate

Validate the affected service, dependent connections, Docker health
where available, and relevant logs. Report unverified dependencies
rather than declaring success.
