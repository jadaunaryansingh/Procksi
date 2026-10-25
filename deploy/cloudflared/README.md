# Cloudflare Tunnel — deployment

Replaces the public IP / open ports on the EC2 box. `cloudflared` runs as a
container (`docker-compose.yml`), makes an **outbound** connection to Cloudflare,
and Cloudflare routes each `*.glapms.in` hostname to the matching frontend
container over the compose network. Nothing listens on a public port anymore.

```
browser ──TLS──> Cloudflare edge ──tunnel(outbound from EC2)──> cloudflared ──http──> {admin,panel,student,mentor}-frontend:80 ──> *-backend
```

Each frontend is nginx that already serves the SPA **and** reverse-proxies
`/api/` + `/auth/` to its backend, so the tunnel only needs the four frontend
containers.

---

## Option A — remotely-managed tunnel (recommended)

Routing lives in the Cloudflare dashboard; the box only holds a token. Matches
the existing "secrets in CI, written to `.env` on deploy" pattern.

### 1. Create the tunnel

Cloudflare **Zero Trust** dashboard → **Networks → Tunnels → Create a tunnel** →
type **Cloudflared** → name it e.g. `glapms-ec2` → **Save**.

On the "Install connector" screen, copy the **token** (the long string after
`--token` in the shown command). Don't run their install command — the compose
service does it.

### 2. Add public hostnames

Still in the tunnel's config → **Public Hostname** tab → add four routes:

| Subdomain | Domain | Path | Service (Type: HTTP) |
|---|---|---|---|
| `admin`   | `glapms.in` | (blank) | `http://admin-frontend:80` |
| `panel`   | `glapms.in` | (blank) | `http://panel-frontend:80` |
| `student` | `glapms.in` | (blank) | `http://student-frontend:80` |
| `mentor`  | `glapms.in` | (blank) | `http://mentor-frontend:80` |

Saving each one **auto-creates the DNS CNAME** (`admin.glapms.in →
<tunnel-id>.cfargotunnel.com`, proxied). Delete the old A records that pointed
`*.glapms.in` at the EC2 IP.

Leave `glapms.in` / `www.glapms.in` alone if the landing site (`apps/main`) is
deployed elsewhere (Pages/Vercel). To serve it from the box too, add a
`main-frontend` service and a fifth hostname.

Per-hostname **Additional application settings → HTTP Settings**: leave
"HTTP Host Header" blank (nginx `server_name` is `localhost` and matches
anything). No "Origin Server Name" / TLS settings needed — the hop to the
container is plain HTTP on a private network.

### 3. Wire the token

- **CI deploy:** add repo secret **`CLOUDFLARE_TUNNEL_TOKEN`** (Settings →
  Secrets and variables → Actions). `deploy-ec2.yml` already writes it into
  `.env` and fails the deploy if it's missing.
- **Manual / first run on the box:** add to `~/Project_Management_System/.env`:
  ```
  CLOUDFLARE_TUNNEL_TOKEN=eyJh...   # from step 1
  ```

### 4. Bring it up

```bash
cd ~/Project_Management_System
docker compose up -d cloudflared
docker compose logs -f cloudflared          # expect: "Registered tunnel connection" x4
docker compose exec cloudflared cloudflared tunnel info glapms-ec2
```

The tunnel dashboard should show **HEALTHY**. Hit `https://admin.glapms.in`.

---

## Option B — locally-managed tunnel (config in this repo)

Use if you want ingress rules version-controlled instead of in the dashboard.

```bash
# one-time, on a machine with cloudflared + `cloudflared login` done:
cloudflared tunnel create glapms-ec2
#   -> writes ~/.cloudflared/<UUID>.json  (the credentials file — treat as a secret)
cloudflared tunnel route dns glapms-ec2 admin.glapms.in
cloudflared tunnel route dns glapms-ec2 panel.glapms.in
cloudflared tunnel route dns glapms-ec2 student.glapms.in
cloudflared tunnel route dns glapms-ec2 mentor.glapms.in
```

Copy `<UUID>.json` to `deploy/cloudflared/credentials.json` on the box
(git-ignored — see below), put the tunnel UUID in `config.yml`, and swap the
compose service to:

```yaml
  cloudflared:
    image: cloudflare/cloudflared:2024.10.1
    container_name: cloudflared
    restart: unless-stopped
    command: tunnel --no-autoupdate --config /etc/cloudflared/config.yml run
    volumes:
      - ./deploy/cloudflared/config.yml:/etc/cloudflared/config.yml:ro
      - ./deploy/cloudflared/credentials.json:/etc/cloudflared/credentials.json:ro
    depends_on: [admin-frontend, panel-frontend, student-frontend, mentor-frontend]
```

`config.yml` is provided in this directory. Add to `.gitignore`:

```
deploy/cloudflared/credentials.json
```

---

## Lock down the box (do this once the tunnel is HEALTHY)

The public IP is now dead weight and an attack surface.

- **EC2 security group — inbound:** remove `80`, `443`, `3000-3003`,
  `8000-8003`. Keep **only** SSH (`22`) from your admin IP — or remove `22` too
  and use **AWS SSM Session Manager**. Outbound stays open (the tunnel needs it:
  `443` to `*.cloudflare.com` / `*.argotunnel.com`, UDP `7844`).
- Confirm nothing is bound to `0.0.0.0`: `sudo ss -tlnp | grep -v 127.0.0.1`
  should show only the Docker proxy on `127.0.0.1`.
- Cloudflare dashboard → the zone → **SSL/TLS → Overview → Full (strict)** is
  fine (edge ↔ browser); the tunnel hop needs no cert.
- **DNS:** every `*.glapms.in` record must be **Proxied** (orange cloud). There
  should be no `A`/`AAAA` record pointing at the EC2 IP anywhere in the zone.

## Gate the admin surface with Cloudflare Access (recommended, ties to the incident)

Zero Trust → **Access → Applications → Add → Self-hosted**:

- **`admin.glapms.in`** — policy: Allow, emails ending `@gla.ac.in` (or an
  explicit list). One-time PIN or Google IdP. This puts a login in front of the
  admin portal at the edge, before any request reaches the container.
- **`panel.glapms.in` path `/admin/sync/*`** — separate application, policy:
  Allow only a service token (for admin-api → panel-api calls) or your admin
  emails. Closes the baked-`ADMIN_API_KEY` exposure at the edge until the
  frontend refactor lands (see `SECURITY_INCIDENT_2026-09-03.md` §2.8).

## Rollback

`docker compose stop cloudflared`, re-open the security-group ports, restore the
old A records. The `127.0.0.1:` port binds mean you must re-add a host reverse
proxy (or change them back to `"3000:80"` etc.) to serve traffic without the
tunnel.

## Notes

- `GOOGLE_REDIRECT_URI=https://admin.glapms.in/auth/google/callback` is
  unchanged — Cloudflare serves that hostname with its edge cert.
- CORS: backends already allow the `https://*.glapms.in` origins.
- `cloudflared` auto-reconnects; `restart: unless-stopped` covers box reboots.
- Bump the pinned image (`cloudflare/cloudflared:2024.10.1`) periodically.
- Metrics/health: `docker compose exec cloudflared cloudflared --version`; add
  `TUNNEL_METRICS: 0.0.0.0:2000` to the service env and curl `/ready` for a
  scripted healthcheck.
