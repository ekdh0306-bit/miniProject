create table if not exists public.inquiries (
  id uuid primary key default gen_random_uuid(),
  author_id uuid not null references auth.users(id) on delete cascade,
  author_name text not null check (char_length(btrim(author_name)) between 1 and 80),
  title text not null check (char_length(btrim(title)) between 1 and 200),
  content text not null check (char_length(btrim(content)) between 1 and 10000),
  view_count integer not null default 0 check (view_count >= 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists inquiries_created_at_idx
  on public.inquiries (created_at desc);
create index if not exists inquiries_author_id_idx
  on public.inquiries (author_id);

create or replace function public.set_inquiries_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists set_inquiries_updated_at on public.inquiries;
create trigger set_inquiries_updated_at
before update of title, content on public.inquiries
for each row execute function public.set_inquiries_updated_at();

alter table public.inquiries enable row level security;

drop policy if exists "inquiries_public_select" on public.inquiries;
create policy "inquiries_public_select"
on public.inquiries for select
to anon, authenticated
using (true);

drop policy if exists "inquiries_authenticated_insert" on public.inquiries;
create policy "inquiries_authenticated_insert"
on public.inquiries for insert
to authenticated
with check ((select auth.uid()) = author_id);

drop policy if exists "inquiries_author_update" on public.inquiries;
create policy "inquiries_author_update"
on public.inquiries for update
to authenticated
using ((select auth.uid()) = author_id)
with check ((select auth.uid()) = author_id);

drop policy if exists "inquiries_author_delete" on public.inquiries;
create policy "inquiries_author_delete"
on public.inquiries for delete
to authenticated
using ((select auth.uid()) = author_id);

revoke all on table public.inquiries from anon, authenticated;
grant select on table public.inquiries to anon, authenticated;
grant insert (author_id, author_name, title, content)
  on public.inquiries to authenticated;
grant update (title, content)
  on public.inquiries to authenticated;
grant delete on table public.inquiries to authenticated;
grant select, insert, update, delete
  on table public.inquiries to service_role;

notify pgrst, 'reload schema';

select to_regclass('public.inquiries') as created_table;
