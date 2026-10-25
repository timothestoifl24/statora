# Status pages

Status pages are public, need no login, and are built under **Status pages** in the admin panel.

## Building a page

**New status page** opens a dialog with the page settings. After creating the page you land in its components editor. Later, **Settings** (on the overview or in the editor) reopens the settings dialog and **Components** opens the editor.

- **Title, slug and description**: the page lives at `/s/<slug>`. The description and footer accept Markdown.
- **Components**: add groups (such as "Websites" or "Infrastructure") and fill them with monitors, each with an optional public name. Drag groups and monitors by their grip handle to reorder them, or drag a monitor into another group. The arrow buttons do the same from the keyboard.
- **Uptime bars**: how much history each component shows. Every option draws 120 bars:

  | Setting | One bar per | Covers |
  |---|---|---|
  | Per minute | minute | the last 2 hours |
  | Per hour | hour | the last 5 days |
  | Per day (default) | day | the last 120 days (about 4 months) |

  Minute and hour bars are calculated from raw check results, so they reach back only as far as `STATORA_HEARTBEAT_RETENTION_DAYS` (default 30 days). Keep it at 5 days or more for hourly bars. A monitor that checks less often than once a minute (or hour) has bars without a check of their own. They continue the previous result, and their tooltip says so.
- **Accent colour and logo**: shown in the header and used for links.
- **Favicon**: the browser-tab icon of this page. Upload a PNG, SVG, ICO, WebP, GIF or JPEG (up to 256 KB) or paste a URL. Without one, the page uses the Statora icon.
- **Published**: unpublished pages return 404.
- **Default page**: served at `/` as well.
- **Show "Powered by Statora"**: on by default; switch it off for a fully white-label page.

The **View status page** button at the top of the editor opens the live page.

Icons and links shown next to components are set on the monitors themselves (see [Monitors](./monitors)), so they're the same on every page.

## What visitors see

- An overall status card: *All Systems Operational*, *Degraded Performance*, *Partial* or *Major System Outage*, or *Under Maintenance*. It's derived from component states and the impact of active incidents, and says how many components are affected.
- Active incidents with their full timeline inside the status card, and upcoming or ongoing maintenance.
- Every component with its icon, its uptime, and 120 uptime bars, per minute, hour or day depending on the page. Hovering a bar shows its uptime and failed checks. Components with a link open the app behind them.
- Groups that expand to show their members.
- Incidents from the last 14 days.
- A light/dark toggle. The page follows the visitor's system setting until they choose, then remembers the choice.

Pages refresh themselves every minute and work without JavaScript, falling back to a plain meta refresh. Times are shown in the visitor's time zone.

## Caching

Each page is rendered from a summary cached in Redis for 30 seconds (`STATORA_PAGE_CACHE_TTL`). Status changes, incidents and edits clear the cache straight away, so the cache never hides news.

## JSON

The same data is available without authentication at `GET /api/v1/public/pages/<slug>/summary`, for example for embedding or custom badges.
