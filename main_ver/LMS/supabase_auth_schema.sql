-- SafeCar authentication phase 1
-- Run this in the Supabase SQL editor before testing /join or /login.
--
-- login_email is a server-only cache used to translate the existing UID login
-- into Supabase Auth's email/password login. It is never returned to a browser
-- by a public profile lookup. Phase 1 accesses profiles only through the Flask
-- server's service-role client.

create table if not exists public.profiles (
    id uuid primary key references auth.users(id) on delete cascade,
    uid text unique not null,
    name text not null,
    role text not null default 'user'
        check (role in ('user', 'admin', 'manager')),
    active boolean not null default true,
    bio text,
    profile_image_path text,
    login_email text unique not null,
    created_at timestamptz not null default now()
);

alter table public.profiles enable row level security;

-- Phase 1 deliberately grants no direct anon/authenticated access to profiles.
-- The service-role key must remain on the Flask server and bypasses RLS.
revoke all on table public.profiles from anon, authenticated;
grant select, update on table public.profiles to service_role;

create or replace function public.handle_new_auth_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
    requested_uid text;
    requested_name text;
begin
    requested_uid := trim(new.raw_user_meta_data ->> 'uid');
    requested_name := trim(new.raw_user_meta_data ->> 'name');

    if requested_uid is null or requested_uid = '' then
        raise exception 'uid metadata is required';
    end if;

    if requested_name is null or requested_name = '' then
        raise exception 'name metadata is required';
    end if;

    insert into public.profiles (
        id, uid, name, role, active, login_email
    )
    values (
        new.id,
        requested_uid,
        requested_name,
        'user',
        true,
        lower(new.email)
    );

    return new;
end;
$$;

create or replace trigger on_auth_user_created
    after insert on auth.users
    for each row execute procedure public.handle_new_auth_user();
