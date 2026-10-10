# Groups

A group is a monitor whose status is calculated from other monitors instead of a network check. Groups show up everywhere a monitor can: on status pages, in uptime history, in incidents and maintenance windows, and in the API.

Create one under **Monitors → New monitor** and choose **GROUP** as the type.

## Stack

*Every member must be healthy.* Use it for services that depend on several parts, for example web front end + API + database.

| Members | Group |
|---|---|
| all up | up |
| any degraded | degraded |
| any in maintenance | maintenance |
| any down | **down** |

## Redundancy

*At least N members must be up.* Use it for clusters and failover pairs, for example two load-balanced nodes where one is enough.

| Members | Group |
|---|---|
| enough members up, none impaired | up |
| enough members up, some down | **degraded** (redundancy reduced). Can be turned off. |
| too few up, but only because of maintenance | maintenance |
| too few up | **down** |

**Members that must be up** sets *N* (default 1). A member that is still within its retries counts as available, so one failed check doesn't flip the group.

## Nesting

Groups can contain groups. For example, a "Checkout" stack can include a "Payment API" redundancy group alongside the front end. Loops are rejected when you save.

## How fast groups react

A group is evaluated on its own interval, and also **immediately whenever one of its members changes status**. The change travels up through nested groups in the same step, so a node failing marks its redundancy group degraded, and any stack containing that group, within the member's own check.

## On status pages

A group appears as one component with its own uptime bars. Visitors can expand it to see each member's status and 90-day uptime. Paused members are hidden.

::: tip Member names are public
Expanded groups show monitor names as they are. If those names contain internal hostnames, rename the monitors before adding the group to a public page.
:::

## API

```json
POST /api/v1/monitors
{
  "name": "Payment API",
  "type": "group",
  "member_ids": [12, 13],
  "config": { "mode": "redundancy", "min_up": 1, "degraded_on_member_failure": true }
}
```
