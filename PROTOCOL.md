# PROTOCOL.md — Reverse-Engineering Urja Meter Ops

> **Document Purpose**: Detailed technical findings from investigating the legacy *Urja Meter Ops* utility portal (`https://urja-ops.flockenergy.tech`). This document details the underlying architecture, discovered endpoints, authentication mechanisms, cryptographic protocols, data schemas, and legacy data quirks.

---

## 1. System Overview & Technology Stack

The Urja Meter Ops portal is an internal web portal used by utility distribution operations staff. Analysis of HTTP headers, JavaScript bundles, and runtime behavior revealed:

- **Framework**: **SvelteKit** with server-side rendering (SSR) and client-side progressive enhancement (`x-sveltekit-page: true`).
- **Authentication**: **Better-Auth** session engine issuing `__Secure-better-auth.session_token` HTTP cookies.
- **Frontend Assets**: Vite-bundled immutable ESM chunks (`/_app/immutable/nodes/...`).
- **Internal APIs**: A mix of SvelteKit form actions, internal `/portal/...` JSON endpoints, SSR hydration payloads (`/__data.json`), and a protected cryptographic bulk export endpoint (`/portal/export`).

---

## 2. Authentication & Session Lifecycle

### 2.1 The Login Mechanism
Authentication is exposed via a standard web form at `/login`. However, programmatic clients must satisfy SvelteKit's built-in CSRF defenses:

1. **Endpoint**: `POST https://urja-ops.flockenergy.tech/login`
2. **Payload format**: `application/x-www-form-urlencoded`
   - `email=operator@urja.local`
   - `password=urja-ops-2026`
3. **Mandatory CSRF Headers**:
   - `Origin: https://urja-ops.flockenergy.tech`
   - `Referer: https://urja-ops.flockenergy.tech/login`
   - *Failure to provide an Origin matching the portal host results in an immediate `HTTP 403 Forbidden` response.*
4. **Successful Response**:
   - Status: `HTTP 200 OK` (SvelteKit action convention)
   - Body: `{"type":"redirect","status":303,"location":"/meters"}`
   - Cookie: `__Secure-better-auth.session_token=<token>; Max-Age=3600; Path=/; HttpOnly; Secure; SameSite=Lax`

### 2.2 Session Verification & Expiry
- Session validity can be probed via `GET /api/auth/get-session`.
- The session payload reveals:
  ```json
  {
    "session": {
      "id": "...",
      "token": "...",
      "userId": "...",
      "expiresAt": "2026-10-25T14:37:50.339Z",
      "createdAt": "...",
      "ipAddress": "..."
    },
    "user": {
      "id": "...",
      "name": "Ops Desk",
      "email": "operator@urja.local"
    }
  }
  ```
- **Session Duration**: Exactly 1 hour (`Max-Age=3600`).
- **Expiration Behavior**: Requests with missing, expired, or invalid session tokens to `/portal/...` return `HTTP 401 Unauthorized` (`{"error":"unauthorized"}`).

---

## 3. Discovered Endpoint Catalog

| Endpoint | Method | Auth Required | Description |
| :--- | :--- | :--- | :--- |
| `/login` | `POST` | None | Authenticates operator; sets session cookie. |
| `/api/auth/get-session` | `GET` | Cookie | Returns session expiry metadata and operator user profile. |
| `/api/auth/sign-out` | `POST` | Cookie | Terminates active session. |
| `/portal/meters/search` | `GET` | Cookie | Paginated meter search (query param `q`, `page`). |
| `/portal/meters/{id}/geo` | `GET` | Cookie | Returns `{ latitude, longitude }` coordinates. |
| `/portal/meters/{id}/energy` | `GET` | Cookie | Time-series consumption interval readings. |
| `/portal/dts` | `GET` | Cookie | Paginated Distribution Transformers (`page`). |
| `/portal/keys` | `GET` | Cookie | Returns dynamic HMAC secret (`data.signingSecret`). |
| `/portal/export` | `GET` | Cookie + HMAC | Bulk dataset export (requires `x-timestamp`, `x-signature`). |
| `/meters/{id}/__data.json` | `GET` | Cookie | SvelteKit SSR serialized nameplate and hierarchy graph. |

---

## 4. The Bulk Export Protocol & HMAC Signing

The portal contains a hidden bulk export mechanism (triggered by the "Export all meters" button on `/transformers`). This is by far the fastest and most complete data retrieval path:

### 4.1 Key Retrieval
A GET request to `/portal/keys` yields:
```json
{
  "data": {
    "signingSecret": "I3dZPPf5CgTp7JyGNMI8i6z8LFR7TmSR"
  }
}
```

### 4.2 Signature Construction
To call `GET /portal/export?page=1`, the client must construct an HMAC-SHA256 signature:

1. **Components**:
   - `METHOD`: `"GET"`
   - `PATH`: `"/portal/export"`
   - `QUERY_STRING`: `"page=1"`
   - `TIMESTAMP`: Current Unix epoch seconds as string (e.g., `"1792936942"`)
2. **Canonical String to Sign**:
   ```
   METHOD\nPATH\nQUERYSTRING\nTIMESTAMP
   ```
   Example:
   ```
   GET
   /portal/export
   page=1
   1792936942
   ```
3. **Algorithm**: `HMAC-SHA256(secret, canonical_string)` formatted as lowercase hex string.
4. **Request Headers**:
   - `x-timestamp: <timestamp>`
   - `x-signature: <hex_digest>`
5. **Replay Window**:
   - Experimental validation revealed a strict **300-second (5-minute) tolerance window**.
   - Requests with timestamps offset by $> 300$ seconds fail with `HTTP 401 {"error":"signature_invalid","message":"Missing or invalid request signature."}`.

---

## 5. Quirks, Surprises, and Data Anomalies

During our deep inspection of all 403 meters and 40 transformers, several significant legacy data quirks were discovered:

### 1. Incompatible Nameplate Schemas (`legacy` vs `v2`)
Smart meters deployed across the utility network report technical nameplates in two completely incompatible formats:
- **`legacy` Meters (238 meters)**: Structured as an array of key-value objects:
  ```json
  "detail": {
    "data": [
      { "parameterName": "Meter ID", "parameterValue": "J100000" },
      { "parameterName": "Serial No", "parameterValue": "SE33962" },
      { "parameterName": "Make", "parameterValue": "HPL" }
    ]
  }
  ```
- **`v2` Meters (165 meters)**: Encoded as a JSON string within a `classData` wrapper using PascalCase keys:
  ```json
  "detail": {
    "classData": "{\"installed_meter\":{\"MeterId\":\"J100004\",\"SerialNo\":\"SE65293\",\"Make\":\"Genus\",\"PhaseType\":\"single\",\"InstallationStatus\":\"Faulty\",\"InstallationType\":\"CT Operated\"}}"
  }
  ```
*Solution in our API*: `MeterService.normalize_meter()` unifies both representations into a standardized `NameplateItem` schema and dictionary.

---

### 2. Conflicting Entity Naming (DT-007 Aliasing)
In the hierarchy data:
- Distribution Transformer code `DT-007` is registered as **`"Sanganer DT 7"`** on several meters and as **`"Old Malviya Nagar Xfmr"`** on others.
- Both refer to the identical electrical asset code (`DT-007`).
*Solution in our API*: The hierarchy engine resolves the canonical name using frequency weighting and reports the conflict in `/api/v1/hierarchy/anomalies`.

---

### 3. Missing / Empty Tier Names in Hierarchy
Multiple records contain empty strings `""` for hierarchy node names or codes:
- Circle `C-01` has empty name on 1 record.
- Circle `C-03` has empty name on 2 records.
- Circle `C-05` has empty name on 1 record.
- Feeder `F-003` has empty name on 1 record.
- Feeder `F-013` has empty name on 1 record.
*Solution in our API*: Automatically backfills missing names from non-empty canonical records for the same tier code.

---

### 4. Multi-Parent Feeder & Substation Topology
The utility network hierarchy does not form a strict tree in raw data; it contains multi-parent mappings:
- Feeder `F-001` is mapped under Substation `SS-01` on some meters, and under Substation `SS-11` on others.
- Feeders `F-002` through `F-012` exhibit similar cross-substation parentage.
*Solution in our API*: Reconstructs a clean primary tree based on dominant parent links while cataloging all multi-parent variants in the audit diagnostics.

---

### 5. Heterogeneous Energy Resolution (30-Min vs Daily Reads)
Not all meters report energy at the same frequency:
- Meters such as `J100000`, `J100001`, `J100004` report **30-minute interval profile data** (337 intervals over 7 days).
- Meters such as `J100100`, `J100200`, `J100300`, `J100400` report **daily midnight billing reads** (8 records over 7 days).
*Solution in our API*: `EnergyService` dynamically measures interval deltas to detect and report `sampling_resolution` in `EnergySummary`.

---

### 6. Hidden Date Filtering in the Energy API
While the legacy web UI always loads a static 7-day window and displays *"No readings in the default window"*, the backend endpoint `/portal/meters/{id}/energy` **actually supports date filtering**:
- `?from=YYYY-MM-DD` (or `DD/MM/YYYY`)
- `?to=YYYY-MM-DD` (or `DD/MM/YYYY`)
Testing verified that passing `?from=2026-06-25&to=2026-06-28` successfully constrains the result set.
*Solution in our API*: First-class support for `from_date` and `to_date` query parameters.

---

### 7. Native Portal Search Limitations
The portal's `/portal/meters/search` only performs prefix matching against `meterId` or `serialNo`.
- Searching `"HPL"` (manufacturer) returns `0` results.
- Searching `"DT-001"` (transformer code) returns `0` results.
*Solution in our API*: Our local indexing service indexes all attributes, enabling full-text search across meter ID, serial, make, transformer, feeder, and zone, plus multi-attribute boolean filters.
