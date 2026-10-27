# Mentor Portal — Email Setup and Operation

Everything the mentor API needs in order to send mail, what it sends, and how
to diagnose it when it stops. Written against the code as it stands, with the
file and line of each claim so it can be re-checked rather than trusted.

---

## 1. Configuration

Six variables, read from the environment (a `.env` file locally, the EC2
`.env` written by `deploy-ec2.yml` in production).

| Variable | Value | Notes |
|---|---|---|
| `MAIL_SERVER` | `smtp.gmail.com` | |
| `MAIL_PORT` | `587` | STARTTLS. Port 465 would need `MAIL_SSL_TLS`. |
| `MAIL_USERNAME` | `aiml_project_coordinator@example.edu` | The Google account the app password belongs to. |
| `MAIL_PASSWORD` | 16-character Google app password | See section 2. |
| `MAIL_FROM` | same as `MAIL_USERNAME` | Falls back to `MAIL_USERNAME` if unset. |
| `MAIL_STARTTLS` | `True` | Only read by the `fastapi_mail` path. |

Defaults live in `app/core/config.py:28-34`. Every field defaults to an empty
string, so a missing variable is not a startup error -- it fails later, at
send time.

**Production reads `MAIL_PASSWORD` from a GitHub secret**
(`deploy-ec2.yml:175`). The secret is only written into the server's `.env`
*during a deploy*, so changing it in repo settings does nothing until the
workflow runs again.

### Spaces in the app password

Google displays app passwords as `xxxx xxxx xxxx xxxx`. Both forms are
accepted, but they are not handled identically:

- `app/api/auth.py:669` calls `.replace(" ", "")`, so the password reset path
  strips spaces itself.
- `app/services/email_service.py:7` passes `settings.MAIL_PASSWORD` straight
  into `ConnectionConfig`, and `config.py` does not strip. SMTP transmits the
  password literally, so this path would send the spaces.

**Store it without spaces.** That is correct for both paths and removes the
question entirely.

---

## 2. Generating the app password

1. Sign in as **`aiml_project_coordinator@example.edu`**. Confirm the account in
   the avatar menu -- a password generated under any other Google account
   produces an error identical to a wrong password.
2. 2-Step Verification must be enabled on that account. App passwords do not
   exist without it.
3. Visit https://myaccount.google.com/apppasswords, create one, and copy the
   16 characters.
4. Update **all four** backends' `.env` files -- `admin-api`, `panel-api`,
   `student-api`, `mentor-api` all authenticate as the same mailbox.
5. Update the `MAIL_PASSWORD` GitHub secret, then run a deploy.

`example.edu` is a Google Workspace domain. A Workspace administrator can
disable app passwords for the whole organisation, in which case a freshly
generated password is still rejected. If everything above is correct and
login still fails, that policy is the remaining explanation and only Procksi IT
can lift it.

---

## 3. What the mentor API sends

Two independent paths. They do not share code, and one can work while the
other fails.

### 3a. Password reset -- direct `smtplib`

`app/api/auth.py:612-713`, endpoint `POST /auth/forgot-password`.

- Refuses any address that is not a known, resettable mentor account.
- Signs a JWT with `SECRET_KEY`, **15 minute expiry** (`auth.py:637-639`).
- Builds the link from `MENTOR_PORTAL_URL`, defaulting to
  `https://mentor.your-domain.com` (`auth.py:643`).
- Sends HTML via `smtplib` with STARTTLS (`auth.py:698-701`).

This path fails loudly and usefully:

| Condition | Response |
|---|---|
| `MAIL_USERNAME` or `MAIL_PASSWORD` empty | `503 SMTP_NOT_CONFIGURED` |
| SMTP raised anything | `500 SMTP_ERROR` with the SMTP text included |

The second is the fastest live diagnostic in the whole system, because the
real SMTP error reaches the HTTP response verbatim.

### 3b. Communication Agent -- `fastapi_mail`

`app/services/communication_service.py`, exposed under
`/api/admin/communication` (`app/api/communication.py:20`) and mounted at
`main.py:247`.

Note the prefix: these endpoints live in the **mentor** service but are
addressed to administrators, and are what the admin portal's Communication
screen calls.

It resolves a named audience segment, renders a template, sends through
`email_service.send_mail`, and logs each dispatch to `email_logs`.

**Seven segments** (`communication_service.py:36-44`): `all_students`,
`team_leaders`, `unassigned_students`, `incomplete_teams`,
`teams_without_mentors`, `mentors`, `specific_team` (this last one requires a
`team_id`).

**Seven templates**: `kickoff`, `team_formation`, `problem_statements`,
`team_add_request`, `proposal_approved`, `proposal_rejected`,
`mentor_onboarding`.

Endpoints: `GET /templates`, `GET /segments`, `POST /send`, `GET /history`,
`POST /schedule`, `POST /schedule-sequence`, `GET /scheduled`,
`POST /scheduled/{id}/cancel`, `POST /run-due`, `POST /broadcast`.

Scheduled sends are fired by a background poller started in `main.py:25-27`,
so a scheduled message depends on the mentor API process staying up.

### 3c. Dead code -- do not rely on it

`email_service.py` also defines six helpers that read like the system's
notification set:

`send_awareness_mail`, `send_proposal_submission_reminder`,
`send_team_formation_reminder`, `send_mentor_allocation_notice`,
`send_presentation_schedule_notice`, `send_result_announcement`

**None of them has a single caller** -- verified by searching the whole
`mentor-api` tree. Only `send_mail` is reached, via `communication_service`.

This matters because the names imply behaviour the mentor API does not have.
In particular, `send_mentor_allocation_notice` here does **not** send the
mentor-allocation email; that is triggered from the admin API. Reading this
file alone would give the wrong idea about what the service does.

---

## 4. Verifying it works

A probe script checks all four backends at once:

```
python3 scripts/smtp_probe.py
```

It attempts a real STARTTLS login per backend, warns if their passwords have
drifted apart, and exits non-zero on any failure. It prints only lengths and
short fingerprints, never the password.

To confirm delivery rather than just authentication:

```
python3 scripts/smtp_probe.py --send you@example.com
```

To test production, which uses the deployed `.env` rather than any local
file, trigger the reset path with a real mentor address:

```
curl -s -X POST https://mentor.your-domain.com/auth/forgot-password \
  -H 'Content-Type: application/json' \
  -d '{"email":"<a real mentor address>"}'
```

A working server returns `{"success": true, ...}`. A broken one returns the
SMTP error in full.

---

## 5. Diagnosing failures

| Symptom | Meaning | Action |
|---|---|---|
| `535 ... BadCredentials` | Gmail rejected the password. | Regenerate under the right account; see section 2. |
| `503 SMTP_NOT_CONFIGURED` | `MAIL_USERNAME` or `MAIL_PASSWORD` empty. | Variable missing from `.env`; in production, the secret was unset at deploy time. |
| Connection timeout | Wrong host/port, or egress blocked. | Check `MAIL_SERVER`/`MAIL_PORT`; confirm the security group allows outbound 587. |
| Local works, production does not | The GitHub secret is unset, or no deploy has run since it was set. | Set the secret, then deploy -- the secret alone changes nothing. |
| Reset link says expired | Tokens live 15 minutes (`auth.py:637`). | Request a new one. |
| Reset link points at the wrong host | `MENTOR_PORTAL_URL` unset or wrong. | Set it; it defaults to `https://mentor.your-domain.com`. |
| Communication sends nothing, no error | The segment resolved to zero recipients. | `communication_service.py:334` only calls the mailer when `msg["emails"]` is non-empty. Check the segment. |
| Scheduled message never fired | The poller did not run. | It starts with the app (`main.py:25`); confirm the process stayed up. |

Gmail returns a byte-identical `535` for a wrong password, a revoked
password, and an account that does not exist. The error alone cannot tell
those apart -- do not read a specific cause into it.

---

## 6. Handling the credential

The previous app password was committed in plaintext across three commits and
eight files, including inside a commit message. It has been removed from the
working tree, but it is permanently in history and in every clone.

When rotating:

- Put the new password only in `.env` files (already gitignored) and the
  GitHub secret.
- Never in source, workflow YAML, or a commit message.
- Never paste it into a chat or issue -- that is the same failure as the
  commit message, in a different place.

Treat any password that has been exposed as compromised and replace it rather
than reusing it.
