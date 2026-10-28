-- SQL Migration 018: managed department (branch) list
-- The Personnel "branch" field becomes a dropdown fed by this list; ADMIN
-- edits it from the System page. Values already stored on people that are not
-- in the list still show up (repository.list_branches merges them).
INSERT INTO system_configurations (key, value)
VALUES ('departments', '["ธุรการ", "กพ", "ยก", "ชุมสาย", "กง", "สำนักงานผู้บังคับบัญชา", "กบ"]'::jsonb)
ON CONFLICT (key) DO NOTHING;
