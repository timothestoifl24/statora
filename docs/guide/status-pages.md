# Status pages

Status pages are public, need no login, and are built under **Status pages** in the admin panel.

## Building a page

- **Title, slug and description**: the page lives at `/s/<slug>`. The description and footer accept Markdown.
- **Components**: add groups (such as "Websites" or "Infrastructure") and fill them with monitors, each with an optional public name. Use the arrows to reorder.
- **Accent colour and logo**: shown in the header and used for links.
- **Published**: unpublished pages return 404.
- **Default page**: served at `/` as well.
- **Show "Powered by Statora"**: on by default; switch it off for a fully white-label page.

The **View status page** button at the top of the editor opens the live page.

## What visitors see

- An overall banner: *All Systems Operational*, *Degraded Performance*, *Partial* or *Major System Outage*, or *Under Maintenance*. It's derived from component states and the impact of active incidents.
- Active incidents with their full timeline, and upcoming or ongoing maintenance.
- Every component with 90 daily uptime bars. Hovering a bar shows that day's uptime and failed checks.
- Groups that expand to show their members.
- Incidents from the last 14 days.
- A light/dark toggle. The page follows the visitor's system setting until they choose, then remembers the choice.

Pages refresh themselves every minute and work without JavaScript, falling back to a plain meta refresh. Times are shown in the visitor's time zone.

## Caching

Each page is rendered from a summary cached in Redis for 30 seconds (`STATORA_PAGE_CACHE_TTL`). Status changes, incidents and edits clear the cache straight away, so the cache never hides news.

## JSON

The same data is available without authentication at `GET /api/v1/public/pages/<slug>/summary`, for example for embedding or custom badges.
