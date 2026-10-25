-- Per-recipient delivery outcomes for the Communication dashboard.
--
-- communication_history has one row per *send*, with recipients stored as a
-- display string ("A Specific Team (2)") -- no addresses and no per-person
-- result. That is why a total SMTP outage was indistinguishable from a clean
-- run: every send was logged "Delivered" regardless.
--
-- This table records what actually happened to each address, so a failure can
-- be seen, counted and retried rather than inferred from a server log nobody
-- reads.

CREATE TABLE IF NOT EXISTS public.email_deliveries (
    id               bigserial PRIMARY KEY,
    communication_id bigint REFERENCES public.communication_history(id) ON DELETE CASCADE,
    email            text NOT NULL,
    -- sent    accepted by the SMTP server
    -- failed  rejected, or the connection never opened
    -- skipped not attempted (blank or malformed address)
    status           text NOT NULL CHECK (status IN ('sent', 'failed', 'skipped')),
    error            text,
    attempted_at     timestamptz NOT NULL DEFAULT now()
);

-- The two queries this table exists to answer: "what happened to this send"
-- and "has this person been failing".
CREATE INDEX IF NOT EXISTS email_deliveries_communication_id_idx
    ON public.email_deliveries (communication_id);
CREATE INDEX IF NOT EXISTS email_deliveries_email_idx
    ON public.email_deliveries (email);

-- Service-role only: these rows carry recipient addresses and are written by
-- the backend, never read from a browser.
ALTER TABLE public.email_deliveries ENABLE ROW LEVEL SECURITY;
