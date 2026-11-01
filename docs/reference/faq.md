# FAQ

### Is Statora free for commercial use?

Yes. Statora is released under the [MIT License](https://github.com/timothestoifl24/statora/blob/main/LICENSE): you can use it, modify it and run it for your business, including for your customers, as long as you keep the copyright and license notice. Third-party components are listed in [THIRD_PARTY_LICENSES.md](https://github.com/timothestoifl24/statora/blob/main/THIRD_PARTY_LICENSES.md).

### How do I report a security problem?

Privately, through [GitHub's private vulnerability reporting](https://github.com/timothestoifl24/statora/security/advisories/new), never in a public issue. If you can't use GitHub, email security@timothestoifl24.dev. The [security policy](https://github.com/timothestoifl24/statora/blob/main/SECURITY.md) has the details.

### Where are checks run from?

From wherever Statora runs. To check from several locations, run an instance in each location.

### Can I run more than one replica?

Yes. Every replica serves the UI and API. A Redis leader lock makes sure exactly one runs the checks, and another takes over within about 15 seconds if it goes away. Migrations are serialized, so replicas can start together.

### Does Redis need persistence or backups?

No. It holds caches, the leader lock and rate-limit counters. Everything important is in PostgreSQL.

### Why does my ping monitor say "ICMP not permitted"?

The container needs the `net.ipv4.ping_group_range` sysctl, or the `NET_RAW` capability. The [Docker](/setup/docker#ping-without-the-sysctl) and [Kubernetes](/setup/kubernetes#probes-and-ping) guides show both.

### How is uptime calculated?

`(up + degraded) / (up + degraded + down)` over the period. Checks inside maintenance windows are left out. A check that fails but is still within its retries counts as up, because the monitor wasn't declared down.

### Do incidents change uptime?

No. Uptime comes from the checks only. Incidents change the page banner: a *critical* incident shows *Major System Outage* even if every check is green.

### Is the status page cached?

For up to 30 seconds, and the cache is cleared as soon as a monitor changes status or an incident or page is edited. Visitors' browsers refresh the page every minute.

### Can I hide "Powered by Statora"?

Yes. Each status page has a switch for it.

### How do I reset a lost admin password?

Run `statora create-admin` inside the container with the same username. It sets a new password.

### Are ITSM ticket numbers visible to the public?

No. Incident ticket numbers and maintenance change numbers, and their links, only appear in the admin panel and the API.
