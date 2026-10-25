# REFLECTION.md — Engineering Reflections

### 1. What assumptions did you make?
I assumed that the legacy portal is an operational read-only source of truth where data mutation is neither expected nor permitted via this integration layer. I also assumed that the meter fleet in this utility instance (~400 smart meters and ~40 distribution transformers in the Jaipur district) fits comfortably in memory, making an eager in-memory index with TTL-based background refresh the optimal architecture for sub-millisecond query latency. Furthermore, I assumed that downstream programmatic consumers (analytics pipelines, field-service mobile apps, billing engines) require clean ISO-8601 timestamps and floating-point numbers rather than the raw DD/MM/YYYY and string representations present in the legacy portal. Lastly, for network hierarchy reconstruction, I assumed that where multi-parent relationships or entity name conflicts exist in raw data, downstream consumers need a deterministic canonical representation accompanied by an explicit audit log rather than silent failure or arbitrary omission.

---

### 2. Which part was the most difficult, and how did you get unstuck?
The most challenging part was reverse-engineering the authentication and bulk export protocol. On initial exploration, standard `POST /login` attempts were abruptly rejected with `HTTP 403 Forbidden` without an error payload. Inspecting the client bundle revealed that SvelteKit's server actions strictly validate the `Origin` header against the request host as part of cross-site request forgery defenses. Once the proper `Origin` and `Referer` headers were provided, login succeeded. Subsequently, inspecting the `/portal/export` endpoint in the frontend JavaScript bundles revealed an HMAC-SHA256 signature requirement. De-obfuscating the client signing function in `transformers.js` (`[e, t, n, i].join("\n")`) allowed me to reconstruct the exact signature payload (`METHOD\nPATH\nQUERYSTRING\nTIMESTAMP`) using the secret retrieved dynamically from `/portal/keys`. Empirical testing with clock skews also uncovered the exact 300-second replay tolerance window.

---

### 3. If you had another day, what would you improve?
With another day, I would enhance the storage and streaming architecture. While an in-memory index is exceptionally fast for a 400-meter fleet, scaling to 100,000+ meters would require swapping the in-memory dictionary for an embedded SQLite/DuckDB database or Redis/PostgreSQL with PostGIS for geospatial indexing (e.g. `ST_DWithin` spatial queries instead of linear Haversine scans). I would also implement persistent incremental change-data-capture (CDC): tracking meter register deltas between polling intervals to generate real-time alerts when sudden power factor drops or sustained voltage sags occur. Finally, I would introduce SSE (Server-Sent Events) or WebSockets to stream live meter telemetry to client dashboards as readings refresh.

---

### 4. What mistake did you make while solving this (there's always one)?
Early in the reverse-engineering phase, I initially tried to reconstruct the entire fleet's details by making concurrent requests to `/portal/meters/search` and scraping `/meters/{id}/__data.json` for all 403 meters sequentially. While this worked, it was noisy, generated hundreds of HTTP requests, and was vulnerable to transient network failures. Only when carefully analyzing the bundle for `transformers.js` did I realize that the portal developers had built an internal `/portal/export` bulk endpoint for CSV/JSON downloads. Recognizing this allowed me to pivot from a fragile, slow crawling strategy to an instantaneous, single-request HMAC-signed bulk sync that fetches all 403 meters in under 300 milliseconds.

---

### 5. If you were reviewing your own submission, what would you criticise?
If reviewing this submission, I would point out that while the in-memory cache is performant, it is currently stateful per process instance. In a horizontally autoscaled multi-replica deployment, each worker process would independently poll the upstream portal and maintain its own cache unless backed by a centralized shared cache like Redis. Additionally, although the API provides rich time-series summaries, the energy endpoint still proxies live requests to `/portal/meters/{id}/energy` on demand rather than pre-indexing historical intervals for all meters in bulk (which was a deliberate trade-off to keep startup sync under one second and avoid bombarding the legacy portal with 400 simultaneous energy queries).
