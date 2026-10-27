-- Rebrand: the chat-availability toggles were created as pms_chat_* (see
-- 202608240001). Renamed in place so every semester keeps its settings.
-- Idempotent: a database built from the renamed 202608240001 already has
-- procksi_chat_* and this is a no-op there.
DO $$
DECLARE
    portal text;
BEGIN
    FOREACH portal IN ARRAY ARRAY['student', 'mentor', 'panel', 'admin'] LOOP
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'semester_config'
              AND column_name = 'pms_chat_' || portal
        ) THEN
            EXECUTE format('ALTER TABLE public.semester_config RENAME COLUMN %I TO %I',
                           'pms_chat_' || portal, 'procksi_chat_' || portal);
        END IF;
    END LOOP;
END $$;

-- Chat bot identity.
UPDATE public.conversation_messages SET sender_id = 'procksibot' WHERE sender_id = 'pmsbot';
UPDATE public.conversation_messages SET read_by = array_replace(read_by, 'pmsbot', 'procksibot')
WHERE 'pmsbot' = ANY(read_by);

-- Storage objects moved from the PMS bucket to Procksi through the Storage API
-- (a SQL update cannot move the underlying files); stored links follow them.
UPDATE public.students  SET avatar_url     = replace(avatar_url, '/PMS/', '/Procksi/')       WHERE avatar_url LIKE '%/PMS/%';
UPDATE public.proposals SET "proposalFile" = replace("proposalFile", '/PMS/', '/Procksi/') WHERE "proposalFile" LIKE '%/PMS/%';
