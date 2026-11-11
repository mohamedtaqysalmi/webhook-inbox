# ADR 0001: HTMX for the inbox UI

## Status

Accepted

## Context

webhook-inbox needs a small UI to create endpoints, inspect stored requests and
trigger replays. The product brief allowed React or HTMX and asked for a
justification.

## Decision

Use server-rendered Jinja templates with HTMX partials for the inbox UI.

## Why not React

- The UI is mostly request/response over the same FastAPI process. There is no
  rich client state, offline mode or component tree that benefits from a SPA.
- A React app would add a Node toolchain, a separate build step and a second
  deployment artifact for what is essentially a table, a detail pane and a form.
- HTMX keeps authorization and filtering on the server next to the SQLite
  queries, which matches how the JSON API already works.
- The portfolio goal is to show FastAPI production habits (limits, SSRF, retention),
  not a front-end architecture exercise.

## Consequences

- The UI ships inside the Python package as templates; `docker compose up` is enough.
- Interactivity is limited to what HTMX partials can express. That is enough for
  MVP. If a future version needs collaborative live updates or a dense editor,
  revisit React (or a similar SPA) as a separate front-end.
