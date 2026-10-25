-- PMSbot posts /report results into the thread as a real, stored message.
--
-- Two changes are needed for that:
--   1. sender_role must admit 'bot'. The four existing values are human roles;
--      a report is written by the system on a person's request, and calling it
--      'admin' or 'student' would make it indistinguishable from something a
--      person typed.
--   2. metadata holds the structured report payload. `body` still carries a
--      readable plain-text rendering, so anything that only knows how to show
--      text (a notification, an export, an older client) shows something
--      sensible rather than nothing.

alter table public.conversation_messages
  drop constraint if exists conversation_messages_sender_role_check;

alter table public.conversation_messages
  add constraint conversation_messages_sender_role_check
  check (sender_role = any (array['admin', 'mentor', 'student', 'panel', 'bot']));

alter table public.conversation_messages
  add column if not exists metadata jsonb;
