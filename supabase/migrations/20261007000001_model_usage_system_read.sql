-- The cumulative AI budget guard (ADR 0012) must know how much has been spent so far. It reads ONE column of the
-- usage ledger on the SYSTEM path: cost_micro_usd, nothing else. A column grant (not a table grant) means
-- `select *`, or any query that names another column, is still refused for app_system.
grant select (cost_micro_usd) on public.model_usage to app_system;
create policy model_usage_system_select on public.model_usage for select to app_system using (true);

do $$
declare
  extra text;
begin
  select string_agg(column_name, ', ') into extra
  from information_schema.role_column_grants
  where table_schema = 'public' and table_name = 'model_usage' and grantee = 'app_system'
    and privilege_type = 'SELECT' and column_name <> 'cost_micro_usd';
  if extra is not null then
    raise exception 'app_system may read only model_usage.cost_micro_usd, not: %', extra;
  end if;
end $$;
