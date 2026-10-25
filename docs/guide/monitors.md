# Monitors

A monitor runs one check on a schedule. Create one under **Monitors → New monitor** (or press <kbd>n</kbd> on the monitor list), or with `POST /api/v1/monitors`. The form opens in a dialog over the list.

## Common settings

| Setting | Default | |
|---|---|---|
| Check every | 60 s | 10 s to 24 h. |
| Timeout | 10 s | Must be shorter than the interval. |
| Retries before down | 1 (UI) / 0 (API) | Extra consecutive failures tolerated. While retrying, the monitor shows as pending and the failures still count as up. |
| Degraded above | none | Responses slower than this (ms) report *degraded* instead of *up*. |
| Active | on | Paused monitors keep their history but aren't checked. |

## Icon and link

Under **Appearance** a monitor can get:

- an **icon**: pick one of the bundled Font Awesome icons (brand logos included), upload an image (PNG, JPEG, WebP, GIF, ICO or SVG, up to 256 KB), or paste an image URL. In the API this is `icon`: `fa:brands:github`, an upload's `media:<sha256>` from `POST /api/v1/media`, or an http(s) URL;
- a **link** (`link_url`) to the app behind the monitor, http(s) only.

Both show in the monitor list and on every status page that includes the monitor. There, the component name links to the app.

## HTTP(S)

Requests a URL and checks the answer.

- **Method**: `GET`, `HEAD`, `POST`, `PUT`, `PATCH`, `DELETE` or `OPTIONS`, optionally with headers (JSON) and a body.
- **Accepted status codes**: codes and ranges, for example `200-299, 301`.
- **Keyword**: text that must appear in the response. Tick *Down if keyword is found* to invert it, for example to alert on `maintenance mode`.
- **Follow redirects** and **verify TLS certificate**: both on by default.

## TCP

Opens a connection to `host:port` and closes it again. It's useful for databases, mail servers and SSH, and for anything that has a port but no HTTP.

## Ping

Sends ICMP echo requests (3 by default). Any packet loss reports *degraded*; no replies at all report *down*. Ping uses unprivileged ICMP sockets, so the container needs the `net.ipv4.ping_group_range` sysctl. The setup guides include it.

## DNS

Resolves a name and optionally checks the answer.

- **Record type**: `A`, `AAAA`, `CNAME`, `MX`, `NS`, `TXT`, `SOA`, `SRV` or `CAA`.
- **Resolver**: a specific nameserver IP, or the system resolver if left empty.
- **Expected value**: the monitor is down unless one of the answers contains this text. It catches records that changed without anyone noticing.

## SQL

Connects to a database, runs a query and optionally checks the result. The target is the database server's host name or IP.

| Engine | Default port | Notes |
|---|---|---|
| PostgreSQL | 5432 | |
| MySQL / MariaDB | 3306 | |
| Microsoft SQL Server | 1433 | Also Azure SQL. |
| Oracle | 1521 | **Database** is the service name, for example `FREEPDB1`. No Oracle Client needed. |

- **Database, user name, password**: the password is stored encrypted. After saving it is never shown again or returned by the API; leave the field empty when editing to keep it.
- **Query**: `SELECT 1` by default (`SELECT 1 FROM DUAL` on Oracle). At most 1,000 rows are read.
- **Expected value**: compared with the first column of the first row as text, either *equals* or *contains*. Booleans read as `true` and `false`; enter `NULL` to expect a NULL value.
- **Minimum rows**: down when the query returns fewer rows, for example to alert when a queue table is empty.
- **TLS**: *Encrypt the connection* turns on TLS; *Verify TLS certificate* (on by default) checks the server's certificate against the system's trusted CAs. Turn verification off only for servers with self-signed certificates.
- The latency includes connecting and logging in, so set *Degraded above* with that in mind.

Some examples:

```sql
-- PostgreSQL: is the replica less than 30 seconds behind?
SELECT extract(epoch FROM now() - pg_last_xact_replay_timestamp()) < 30
-- expected value: true

-- MySQL: jobs waiting for more than ten minutes (down if there are any)
SELECT COUNT(*) FROM jobs WHERE status = 'queued' AND created_at < NOW() - INTERVAL 10 MINUTE
-- expected value: 0
```

::: warning Use a read-only database user
The query runs in a read-only transaction that is always rolled back: PostgreSQL and MySQL reject writes, and SQL Server undoes them. Oracle can't block statements like `CREATE TABLE` this way, so Oracle queries must start with `SELECT` or `WITH`. Still, give Statora its own user that can only read what the query needs.
:::

## What you see

- The **dashboard** shows how many monitors are up, then every monitor with its last 30 checks, 24-hour uptime and latency, failing ones first. It refreshes itself every 15 seconds. Search with <kbd>/</kbd>, filter by problems or type, and expand groups to see their members.
- The **tile view** (the grid button above the list) shows the same monitors as tiles; `/admin?kiosk=1` shows them full screen without the sidebar, for a wallboard.
- Each row on the dashboard has an options menu (<kbd>⋮</kbd>, for editors and admins) to **pause or resume** the monitor without leaving the list, **clone** it, or edit it.
- The **detail page** adds a 24-hour latency chart, the list of status changes, uptime over 24 h and 30 days, and the groups the monitor belongs to. It refreshes itself too.

## Cloning

**Clone** opens the new-monitor form filled in from the original: same type, target, interval, timeout, retries, check settings and (for groups) members, with "(copy)" added to the name. Nothing is saved until you click **Create monitor**, so you can change the name or target first. A stored SQL password is carried over (still encrypted) unless you type a new one. History, status-page placements and memberships in other groups are not copied.
