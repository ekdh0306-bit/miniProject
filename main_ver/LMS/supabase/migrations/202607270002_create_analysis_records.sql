create table if not exists public.media_files (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  original_name text not null,
  storage_path text not null unique,
  file_type text not null check (file_type in ('IMAGE', 'VIDEO')),
  memo text,
  uploaded_at timestamptz not null default now()
);

create table if not exists public.analysis_results (
  id uuid primary key default gen_random_uuid(),
  media_id uuid not null unique references public.media_files(id) on delete cascade,
  status text not null default 'PENDING'
    check (status in ('PENDING', 'SUCCESS', 'FAIL', 'UNAVAILABLE')),
  result_json jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists media_files_owner_uploaded_idx
  on public.media_files (owner_id, uploaded_at desc);

alter table public.media_files enable row level security;
alter table public.analysis_results enable row level security;

drop policy if exists "media_owner_all" on public.media_files;
create policy "media_owner_all" on public.media_files
for all to authenticated
using ((select auth.uid()) = owner_id)
with check ((select auth.uid()) = owner_id);

drop policy if exists "analysis_owner_select" on public.analysis_results;
create policy "analysis_owner_select" on public.analysis_results
for select to authenticated
using (exists (
  select 1 from public.media_files
  where media_files.id = analysis_results.media_id
    and media_files.owner_id = (select auth.uid())
));

grant select, insert, update, delete on public.media_files to service_role;
grant select, insert, update, delete on public.analysis_results to service_role;

insert into storage.buckets (id, name, public)
values ('analysis-media', 'analysis-media', false)
on conflict (id) do update set public = false;

notify pgrst, 'reload schema';

select
  to_regclass('public.media_files') as media_table,
  to_regclass('public.analysis_results') as result_table;
