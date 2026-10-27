-- Procksi-Chat availability, per portal, per semester.
--
-- One boolean per portal so a coordinator can turn chat on for, say, mentors
-- and students while leaving panel off. Scoped to semester_config because the
-- admin portal's global semester filter already selects a row here, so the
-- toggle follows whichever semester is being viewed.
--
-- Default false: a new semester starts with chat off and is opted in
-- deliberately, rather than inheriting a previous semester's state.
--
-- NOT NULL so the frontend never has to distinguish false from missing.

ALTER TABLE public.semester_config
    ADD COLUMN IF NOT EXISTS procksi_chat_student boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS procksi_chat_mentor  boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS procksi_chat_panel   boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS procksi_chat_admin   boolean NOT NULL DEFAULT false;
