# Overview

Statora watches your services, keeps their history and publishes what it sees on status pages. This guide walks through the building blocks. If you haven't installed it yet, start with [setup](/setup/).

## The building blocks

| Concept | What it is |
|---|---|
| **Monitor** | One check against one target: an HTTP endpoint, a TCP port, a host to ping, a DNS record, or a database query. |
| **Group** | A monitor whose status comes from other monitors: a *stack* (all must be healthy) or a *redundancy group* (enough must be up). |
| **Status page** | A public page made of component groups, each listing monitors under public names. |
| **Incident** | A human-written account of a problem, with a timeline of updates, shown on a status page. |
| **Maintenance** | A planned window. Affected monitors show as *under maintenance*, and the time doesn't count as downtime. |

## Statuses

Every monitor is in one of these states:

| Status | Meaning |
|---|---|
| <span class="status-legend" style="color:#2fb344">Up</span> | The last check passed. |
| <span class="status-legend" style="color:#f59f00">Degraded</span> | It works, but slower than its threshold, or a redundancy group lost a member. |
| <span class="status-legend" style="color:#d63939">Down</span> | Checks failed, after the configured retries. |
| <span class="status-legend" style="color:#4299e1">Maintenance</span> | Inside a maintenance window. |
| <span class="status-legend" style="color:#9aa4b2">Pending</span> | Not checked yet, paused, or failing but still within its retries. |

## How a check flows

1. The scheduler runs each active monitor on its interval.
2. A failure becomes **down** only after `retries` failures in a row. Before that, it's pending.
3. Every result is stored as a heartbeat and rolled up into daily statistics, which feed the 90-day bars.
4. When a monitor changes status, every group containing it is re-evaluated immediately, and status pages are refreshed.

## Roles

| Role | Can |
|---|---|
| **Viewer** | See everything in the admin panel; read-only API access. |
| **Editor** | Manage monitors, groups, status pages, incidents and maintenance. |
| **Admin** | Everything, including users and authentication providers. |
