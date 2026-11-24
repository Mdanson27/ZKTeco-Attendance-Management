# Contabo deployment — development only

No VPS has been provisioned. Keep live reception disabled until the pilot is approved.
Use a supported Ubuntu LTS server, SSH keys, a non-root sudo operator, security updates,
Docker Engine with Compose v2, and host Nginx. Do not disable existing SSH access
until a second key-authenticated session has been tested. Restrict SSH to approved
management IPs or a VPN; expose only required HTTPS/ACME ports. Never expose 4370,
8765, or PostgreSQL directly.

1. Clone the repository on the VPS; pin a reviewed commit.
2. Copy deploy/.env.example to deploy/.env; chmod 600. Obtain restricted
   attendance_runtime connection URL from Neon; require TLS. Do not use the owner.
   Set the confirmed Neon Auth base URL. Keep registry empty and live disabled.
3. Run from repository root:
   docker compose --env-file deploy/.env -f deploy/compose.yaml config --quiet
   docker compose --env-file deploy/.env -f deploy/compose.yaml up -d --build
   curl --fail http://127.0.0.1:8765/api/health
4. Configure DNS and issue a valid certificate with an approved ACME procedure.
   Adapt nginx-workspace.conf.example; validate nginx -t before reload.
   Only HR workspace paths are publicly routed. No ADMS public route.
5. Verify sign-in and organization/branch isolation with synthetic accounts.
   Do not import client records until access and retention controls are accepted.
6. For synthetic protocol tests, use local loopback from the server with an
   authorized test-only device and random token digest in the private registry.
   Do not log tokens or request bodies.
7. Physical pilot requires exact firmware, existing HR software configuration,
   approved device identity binding (native authentication or private VPN with
   authenticated ingress), rollback plan and confirmation of coexistence.
   Do not expose an unauthenticated scanner port or trust serial alone.
   The current compose explicitly prevents live device ingestion.
8. Before release: run the CI suite, verify database transactions and retries,
   backup and restore procedures, scoped HR permissions, actual firmware responses,
   rate limiting, retention and monitoring. Configure external HTTPS uptime checks
   and database readiness monitoring; container health alone only checks liveness.

Rollback: preserve the previous reviewed commit/image and environment, stop the
new container, redeploy the previous reviewed image, and validate health.
Do not roll back database data or migrations automatically. The public Pages demo
remains independent. This deployment serves the authenticated workspace at
/workspace/ on the VPS, not GitHub Pages.

Known gaps: full sign-in UI, authenticated write endpoints, processing worker,
correction approvals, physical protocol validation, VPN adapter, database
readiness probe, and real integration testing. No claim of production readiness.
