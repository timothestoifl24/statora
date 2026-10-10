# Incidents & maintenance

## Incidents

An incident tells visitors what's going on in your own words. Report one under **Incidents → Report incident**:

- **Status page**: where it's shown.
- **Impact**: *none*, *minor*, *major* or *critical*. Active incidents raise the page banner, so a *critical* incident shows *Major System Outage* even when every check is green.
- **Status**: *investigating* → *identified* → *monitoring* → *resolved*.
- **Message**: the first update. Markdown is supported and sanitised.
- **Affected monitors**: picked with the two-column selector.
- **Ticket number and URL**: a reference to your ITSM tool (for example `INC0012345`). These stay **internal**: they show in the admin panel and the API, never on the public page.

On the incident page, post updates as the situation develops. Choosing *resolved* closes the incident and moves it to *past incidents*; it can be reopened. **Edit details** changes the title, impact and ticket reference afterwards.

## Maintenance windows

Schedule planned work under **Maintenance → Schedule maintenance**:

- **Window**: start and end, in UTC.
- **Affected monitors**: inside the window they report *maintenance*, and that time doesn't count against their uptime. Groups that are short of capacity only because of maintenance show *maintenance* too, not an outage.
- **Status pages**: the window is announced as *scheduled* beforehand and *in progress* while it runs.
- **Change number and URL**: the change ticket from your ITSM tool. Like incident tickets, these stay internal.
