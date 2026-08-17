-- HANZ SWING DISCOUNT + FUNDAMENTAL INTELLIGENCE V2
-- Run once in Supabase SQL Editor.
-- Safe to run after V1: ADD COLUMN IF NOT EXISTS is idempotent.

alter table public.hanz_swing_signal_monitor
add column if not exists analyst_target_mean numeric,
add column if not exists analyst_target_median numeric,
add column if not exists analyst_target_low numeric,
add column if not exists analyst_target_high numeric,
add column if not exists analyst_upside_pct numeric,
add column if not exists target_discount_pct numeric,
add column if not exists week52_high numeric,
add column if not exists week52_low numeric,
add column if not exists week52_discount_pct numeric,
add column if not exists week52_position_pct numeric,
add column if not exists discount_score numeric,
add column if not exists discount_label text,
add column if not exists discount_confidence text,
add column if not exists discount_reason text,

add column if not exists fundamental_score numeric,
add column if not exists fundamental_label text,
add column if not exists fundamental_confidence text,
add column if not exists fundamental_coverage_pct numeric,
add column if not exists fundamental_reason text,

add column if not exists sector text,
add column if not exists industry text,
add column if not exists revenue_growth_pct numeric,
add column if not exists net_income_growth_pct numeric,
add column if not exists roe_pct numeric,
add column if not exists roa_pct numeric,
add column if not exists debt_to_equity numeric,
add column if not exists operating_cash_flow numeric,
add column if not exists free_cash_flow numeric,
add column if not exists net_margin_pct numeric,
add column if not exists operating_margin_pct numeric,
add column if not exists pe_ratio numeric,
add column if not exists pb_ratio numeric;

create index if not exists idx_hanz_swing_monitor_discount_score
on public.hanz_swing_signal_monitor(discount_score desc);

create index if not exists idx_hanz_swing_monitor_fundamental_score
on public.hanz_swing_signal_monitor(fundamental_score desc);

create index if not exists idx_hanz_swing_monitor_fundamental_label
on public.hanz_swing_signal_monitor(fundamental_label);

create index if not exists idx_hanz_swing_monitor_sector
on public.hanz_swing_signal_monitor(sector);
