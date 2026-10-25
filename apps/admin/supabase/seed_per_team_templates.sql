-- Per-team personalized-send templates.
--
-- Authored specifically for the "Per-Team Personalized Send" page
-- (admin -> Communication -> Per-Team). They use ONLY merge fields that the
-- per-team mail-merge resolves per team:
--   {team_id} {team_name} {project_title} {leader_name} {mentor_name}
--   {members} {member_count} {domain} {semester}
-- They deliberately avoid {date}/{time}/{deadline}/{name}, which have no
-- per-team value and would render as literal placeholders in the email.
--
-- Bodies are HTML (the per-team page sends with the HTML toggle on) and are
-- laid out one block per line with a heading + signature, so they stay clean
-- and editable in the compose box. Idempotent: inserts only missing titles.

insert into public.communication_templates (title, subject, body)
select v.title, v.subject, v.body
from (values
    ('Weekly Check-in',
     'Weekly Check-in: {team_name}',
     $body$<h2 style="margin:0 0 12px">Weekly Progress Check-in</h2>
<p>Dear <b>{team_name}</b> ({project_title}),</p>
<p>This is your weekly progress check-in. Please share an update on your work with your mentor <b>{mentor_name}</b> on the portal.</p>
<p>{leader_name}, kindly make sure all {member_count} members have logged their contributions this week.</p>
<p style="margin-top:16px">Regards,<br/><b>PMS Admin</b></p>$body$),

    ('Mentor Sync Reminder',
     'Mentor Sync Reminder: {team_name}',
     $body$<h2 style="margin:0 0 12px">Mentor Sync Reminder</h2>
<p>Dear <b>{team_name}</b>,</p>
<p>A reminder to meet your assigned mentor <b>{mentor_name}</b> this week to review progress on <b>{project_title}</b>.</p>
<p>Please come prepared with your latest work and any open questions.</p>
<p style="margin-top:16px">Regards,<br/><b>PMS Admin</b></p>$body$),

    ('Confirm Team Roster',
     'Confirm Your Team Roster: {team_name}',
     $body$<h2 style="margin:0 0 12px">Confirm Your Team Roster</h2>
<p>Dear <b>{leader_name}</b>,</p>
<p>Please confirm the roster for <b>{team_name}</b>. We currently have <b>{member_count}</b> members on record:</p>
<blockquote style="margin:12px 0;padding:10px 14px;border-left:3px solid #4f46e5;background:#f8fafc">{members}</blockquote>
<p>If anything is incorrect, please update it on the portal at the earliest.</p>
<p style="margin-top:16px">Regards,<br/><b>PMS Admin</b></p>$body$),

    ('Report Submission Reminder',
     'Report Due: {team_name}',
     $body$<h2 style="margin:0 0 12px">Report Submission Reminder</h2>
<p>Dear <b>{team_name}</b> ({project_title}),</p>
<p>This is a reminder to submit your project report on the portal.</p>
<p>{leader_name}, please coordinate with your team so the submission is complete and uploaded on time.</p>
<p style="margin-top:16px">Regards,<br/><b>PMS Admin</b></p>$body$),

    ('Progress Appreciation',
     'Well Done, {team_name}',
     $body$<h2 style="margin:0 0 12px">Great Work This Week</h2>
<p>Dear <b>{team_name}</b>,</p>
<p>Your mentor <b>{mentor_name}</b> has noted strong progress on <b>{project_title}</b>.</p>
<p>Keep up the excellent work and carry the momentum into your next milestone.</p>
<p style="margin-top:16px">Regards,<br/><b>PMS Admin</b></p>$body$),

    ('Inactivity Nudge',
     'Action Needed: {team_name}',
     $body$<h2 style="margin:0 0 12px">We Have Not Heard From You</h2>
<p>Dear <b>{team_name}</b> ({project_title}),</p>
<p>We have not seen recent activity from your team. Please connect with your mentor <b>{mentor_name}</b> and post an update on the portal so we can support you where needed.</p>
<p>{leader_name}, please take the lead on this.</p>
<p style="margin-top:16px">Regards,<br/><b>PMS Admin</b></p>$body$)
) as v(title, subject, body)
where not exists (
    select 1 from public.communication_templates t where t.title = v.title
);
