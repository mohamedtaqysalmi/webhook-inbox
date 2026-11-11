# Security policy

## Reporting a vulnerability

Please do not open a public issue for security problems. Use the "Report a vulnerability" button on the
[Security tab](https://github.com/mohamedtaqysalmi/webhook-inbox/security/advisories/new) of this repository.
That opens a private advisory only the maintainer can see.

This is a solo-maintained project, so a first reply can take a few days. Include the version or commit,
what you found, and steps to reproduce.

## Supported versions

Only the latest release tag and the tip of `main` are supported.

## Threat notes for operators

webhook-inbox is meant to be self-hosted. Treat endpoint tokens as secrets: anyone who knows a token
can read stored bodies and trigger replays for that endpoint. Do not expose an open create-endpoint
surface to the public internet without an auth layer in front.

### Replay SSRF protection

`POST .../replay` validates the target URL before the outbound request:

- Only `http` and `https` are allowed.
- URLs with embedded credentials are rejected.
- Hostnames such as `localhost` and cloud metadata names are blocked by default.
- Literal IPs and every address returned by DNS resolution are checked; private, loopback,
  link-local, multicast, reserved and unspecified ranges are blocked unless
  `WEBHOOK_INBOX_ALLOW_PRIVATE_REPLAY_TARGETS=true`.

Residual risk: DNS can change between the check and the connect (DNS rebinding). The MVP does not
pin the resolved address on the socket. Keep private replay disabled in shared environments, and put
the service behind a network policy that cannot reach sensitive internal ranges when possible.

### Other limits

- Request bodies are capped (`WEBHOOK_INBOX_MAX_BODY_BYTES`); oversized bodies get HTTP 413 while streaming.
- Stored headers are capped by bytes; overflow is dropped and flagged.
- Create and receive routes share a per-IP sliding-window rate limit (`WEBHOOK_INBOX_RATE_LIMIT_PER_MINUTE`).
- Retention deletes old rows (`WEBHOOK_INBOX_RETENTION_DAYS`).
- Source IP is the direct peer address; `X-Forwarded-For` is not trusted.
