# Monitors

A monitor runs one check on a schedule. Create one under **Monitors → New monitor**, or with `POST /api/v1/monitors`.

## Common settings

| Setting | Default | |
|---|---|---|
| Check every | 60 s | 10 s to 24 h. |
| Timeout | 10 s | Must be shorter than the interval. |
| Retries before down | 1 (UI) / 0 (API) | Extra consecutive failures tolerated. While retrying, the monitor shows as pending and the failures still count as up. |
| Degraded above | none | Responses slower than this (ms) report *degraded* instead of *up*. |
| Active | on | Paused monitors keep their history but aren't checked. |

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

## What you see

- The **dashboard** shows every monitor with its last 30 checks, 24-hour uptime and latency, and refreshes itself every 15 seconds.
- The **detail page** adds a 24-hour latency chart, the list of status changes, uptime over 24 h and 30 days, and the groups the monitor belongs to.
