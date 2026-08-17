docker exec adms_postgres psql -U adms -d adms << 'SQLEOF'
SELECT scan_time, raw_payload->>'timestamp' AS raw_ts FROM attendance_logs ORDER BY scan_time;
SQLEOF