-- A run's steps now come from its workflow definition (registry/workflows.yaml), so the number of steps is no
-- longer fixed at 14. Forward-only: the range widens to 1..64 (the loader's own maximum); the unique (run_id, n)
-- key, the owner/case foreign key and every RLS policy are untouched.
alter table public.workflow_steps drop constraint workflow_steps_n_check;
alter table public.workflow_steps add constraint workflow_steps_n_range check (n between 1 and 64);
