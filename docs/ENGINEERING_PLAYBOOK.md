# Engineering Playbook & Permanent Quality System

**Applicability:** HoReCa One, School ERP, Pharmacy ERP, Retail POS, and all future enterprise software systems.  
**Objective:** Eliminate recurring bugs, architectural missteps, security vulnerabilities, database corruption, and wasted engineering effort through codified, evidence-based rules and pre-flight checklists.

---

## PART 1: CODIFIED ARCHITECTURAL & CODING RULES

### 1. Security & Authentication (`SEC-xxx`)

- **`SEC-001: Zero Cleartext Credentials`**
  - Passwords, PINs, recovery codes, and secret API keys must **never** be stored in cleartext on disk, in SQLite databases, in JSON files, in log streams, or transmitted unencrypted across the network.
  - All credentials must be hashed using cryptographically salted algorithms (e.g., PBKDF2-SHA256 with $\ge 100,000$ iterations or Argon2id) with unique, cryptographically random per-instance salts.
  - Client devices must receive only redacted boolean status flags (e.g., `adminPinSet: true`), never raw or hashed secrets.

- **`SEC-002: Strict Multi-Tenant Enforcement`**
  - Every incoming API request, sync packet, or database query must validate the tenant identifier (`hotel_id`, `school_id`, `org_id`).
  - Cryptographic token validity (JWT/HMAC signature) is **insufficient** on its own; the server must explicitly assert `assert token.tenant_id == node.tenant_id`. Cross-tenant requests must immediately fail closed with `403 Forbidden`.

- **`SEC-003: Cryptographic Rigor in Licensing & Signatures`**
  - Never implement security checks using mock string prefixes (e.g., checking if a signature starts with `"forged"` or `"invalid"`).
  - All offline license updates, software activations, or permission delegations must use standard asymmetric cryptographic primitives (e.g., ECDSA over NIST P-256 with SHA-256 or Ed25519) with pinned public keys and hardware-machine binding.

---

### 2. Database & Data Integrity (`DB-xxx`)

- **`DB-001: Exact Integer Arithmetic for Money`**
  - **Never** store or calculate monetary amounts using IEEE-754 floating-point types (`FLOAT`, `DOUBLE`, `REAL`).
  - All currency calculations and database columns must use 64-bit integer base units (e.g., paise in INR, cents in USD, cents in EUR).
  - Convert to decimal representation only at the final display/UI formatting boundary:
    $$\text{Display} = \frac{\text{Amount in Paise}}{100}$$

- **`DB-002: Financial Record Immutability (No Hard Deletes)`**
  - Confirmed bills, invoices, payments, tax ledger items, and stock consumption movements must **never** be physically deleted (`DELETE FROM ...`) via ordinary user actions or sync mutations.
  - Corrections must follow double-entry accounting principles: audited cancellations with mandatory role elevation, credit notes, or explicit offsetting reversals that preserve the complete audit trail.

- **`DB-003: Safe Backup Restoration Safeguards`**
  - Database restoration must **never** overwrite an active, running database file in place.
  - The restore engine must:
    1. Validate tenant identity (`expected_tenant_id`) matching archive metadata before touching disk.
    2. Execute `PRAGMA integrity_check` on the backup file in an isolated temporary location.
    3. Fail closed if the target destination already contains an existing database file; restorations must target a clean, empty directory.

- **`DB-004: Idempotent Migration Ordering`**
  - Database schema upgrades must be written idempotently.
  - All base tables must be created before any conditional column additions (`ALTER TABLE ... ADD COLUMN ...`).
  - Guard migrations with catalog inspection (`PRAGMA table_info`) to prevent crashes on fresh database initializations.

---

### 3. Concurrency, Outbox & Synchronization (`SYNC-xxx`)

- **`SYNC-001: Monotonic Checkpoints & Stale Overwrite Prevention`**
  - Synchronization envelopes must enforce monotonically increasing version or sequential cursor numbers (`doc_version`, `seq`).
  - An older or delayed operation received out-of-order must **never** overwrite a newer confirmed transaction or lower cloud audit checkpoints.
  - Conflicted, out-of-sequence, or differing payloads must be safely quarantined into an audited conflict table (`sync_conflicts`) without halting the primary replication stream.

- **`SYNC-002: Exact Tuple Acknowledgments`**
  - Sync acknowledgments must never use loose string tokens or count unverified rows.
  - Acknowledgments must return an exact verification tuple: `(op_id, tenant_id, committed_payload_checksum)`.
  - The sender must only purge outbox queue items whose checksum exactly matches the cloud-acknowledged commit hash.

- **`SYNC-003: Non-Blocking Outbox Dispatch`**
  - Network I/O and cloud synchronization dispatchers must **never** execute while holding an active database write transaction lock.
  - Transactions must commit locally in SQLite first; the background dispatcher pulls unacknowledged records asynchronously to avoid blocking local point-of-sale checkout during network latency or cloud outages.

- **`SYNC-004: Permanent Rejections Never Block the Queue`** (from BUG-0009)
  - Every server error code must be classified as *retry later* (network, 5xx, auth, payment) or *permanent* (unsupported module, payload mismatch, stale record).
  - A permanent rejection is held for review with its full payload and removed from the send queue at once. An op that can never succeed must not stay at the head of an ordered queue.
  - When a new rejection code is added on the server, the client classification and a loopback test must be updated in the same change.

---

### 4. Architecture & Offline-First Operation (`ARCH-xxx`)

- **`ARCH-001: Absolute Local Autonomy`**
  - The local on-premise installation (counter, clinic, school office) must remain 100% operational when the internet is completely disconnected.
  - Core business workflows (billing, receipt printing, kitchen ticketing, student attendance, medicine dispensing) must execute locally against local SQLite with zero dependencies on remote cloud round-trips.

- **`ARCH-002: Staging Queue for Unverified Inbound Events`**
  - Remote or unauthenticated input (guest QR orders, online web orders, external webhook events) must **never** be written directly into active operator carts, inventory deduction pipelines, or financial balances.
  - All external inputs must be isolated in an authenticated review staging queue (`/api/q/inbound-qr`) requiring explicit operator review and confirmation before affecting live operations.

- **`ARCH-003: Single-Writer Process Isolation`**
  - Database write connections must be managed through a single designated writer process or shared connection pool with explicit WAL (Write-Ahead Logging) mode and busy timeouts ($\ge 5,000\text{ ms}$).
  - Multiple concurrent background threads or worker processes must never attempt uncoordinated write operations on SQLite files.

---

### 5. Testing & Empirical Verification (`TEST-xxx`)

- **`TEST-001: Empirical Proof Over Assumptions`**
  - Never mark an engineering task, bug fix, or security patch as complete based solely on conversational summaries or visual inspections.
  - Completion requires empirical evidence: executing the automated test suite, verifying exit codes ($0$), and logging exact execution metrics.

- **`TEST-002: Multi-Platform CI Coverage`**
  - Software running on customer premises must be tested against target operating environments (Windows EXE, Linux runners, Chromium browser viewports) in automated CI.
  - Mocked network environments must be supplemented with end-to-end loopback tests exercising genuine HTTP request/response serialization.

- **`TEST-003: Hardware Output Is Verified as Bytes, Then on Paper`** (from BUG-0011)
  - Printer output is decoded byte by byte in CI: only known commands, every text line within the paper width (32 columns at 58 mm, 48 at 80 mm), exactly one cut, drawer only on a first cash print.
  - Byte-level tests never count as physical printer validation; the physical gate stays open until a person checks the paper.

- **`TEST-004: Long-Run Evidence States Its Real Duration`**
  - A soak or outage test reports the duration it actually completed. A shorter run is never presented as evidence for a longer requirement.

---

## PART 2: NEW SOFTWARE PROJECT STARTER CHECKLIST

Use this 17-dimension checklist when starting any new software application (School ERP, Pharmacy ERP, Retail POS, Warehouse Management, etc.).

```
================================================================================
          NEW SOFTWARE PROJECT STARTER CHECKLIST (17 DIMENSIONS)
================================================================================
```

### 1. Requirements & Domain Modeling
- [ ] Has the business domain been mapped with concrete entities, states, and lifecycle transitions (e.g., Draft $\to$ Confirmed $\to$ Settled $\to$ Cancelled)?
- [ ] Are edge cases defined upfront (returns, refunds, cancellations, split payments, partial deliveries)?
- [ ] Have non-functional requirements (operating hours, offline tolerance, concurrency scale) been quantified?

### 2. Architecture & System Boundaries
- [ ] Is the primary boundary clearly defined (Offline-First local node vs Cloud-Native centralized service)?
- [ ] Are third-party boundaries (printers, SMS/WhatsApp gateways, payment scanners) abstracted behind clean adapter interfaces?
- [ ] Does the architecture enforce single-source-of-truth ownership for every business entity?

### 3. Technology Stack Selection
- [ ] Are selected technologies battle-tested, stable, and easily deployable on target client hardware (e.g., Python + SQLite for desktop, Node/Go for edge)?
- [ ] Does the technology avoid heavy, unneeded runtimes on resource-constrained client machines (e.g., 4GB RAM POS hardware)?
- [ ] Are dependencies minimal, inspectable, and secure?

### 4. Simplicity & YAGNI Discipline
- [ ] Is the architecture strictly sized for current and near-term requirements without premature multi-service or micro-framework complexity?
- [ ] Are code paths direct and discoverable without excessive abstraction layers, metaprogramming, or unused generic design patterns?

### 5. Security & Authentication / Authorization
- [ ] Are all credentials hashed with PBKDF2-SHA256 / Argon2id using cryptographically secure random per-instance salts?
- [ ] Is tenant isolation enforced at every layer (`assert request.tenant_id == node.tenant_id`)?
- [ ] Are administrative roles partitioned (e.g., Cashier cannot cancel bills, view owner profit reports, or reset security PINs)?
- [ ] Are API endpoints protected against unauthorized access, replay attacks, and rate abuse?

### 6. Database Design & Schemas
- [ ] Are financial, stock, and inventory balances calculated in exact integer base units (paise/cents, integer grams/milligrams)?
- [ ] Are tables normalized with foreign key constraints, unique business indexes, and strict NOT NULL constraints where appropriate?
- [ ] Are database schema migrations automated, versioned, and guaranteed idempotent (`CREATE TABLE IF NOT EXISTS`, conditional `ALTER TABLE`)?

### 7. Backup, Restore & Disaster Recovery
- [ ] Is automated, scheduled backup configured with zero impact on active counter transactions (e.g., SQLite online backup API)?
- [ ] Does the restore process mandate tenant validation (`expected_tenant_id`) and integrity verification (`PRAGMA integrity_check`)?
- [ ] Does restoration fail closed to prevent accidental in-place overwriting of active databases?

### 8. Concurrency & Locking
- [ ] Is SQLite configured in WAL (Write-Ahead Logging) mode with adequate busy timeouts ($\ge 5,000\text{ ms}$) and 64MB cache tuning?
- [ ] Are database writes structured into short, atomic transactions?
- [ ] Are sequence counters (bill numbers, invoice numbers, receipt IDs) generated atomically without race conditions?

### 9. Offline-First & Network Partition Resilience
- [ ] Can the entire application operate indefinitely without an active internet connection?
- [ ] Does the synchronization engine queue mutations in a durable local outbox table?
- [ ] Are conflicting remote edits quarantined safely without clobbering local cashier operations?

### 10. Input Validation & Data Cleansing
- [ ] Is every external input (HTTP payload, query parameter, CSV import, QR scan) strictly validated against an explicit schema?
- [ ] Are string inputs sanitized against SQL injection, XSS, and command injection?
- [ ] Are impossible values (negative prices, zero-length barcodes, future timestamps) rejected at the boundary?

### 11. UI/UX & Operator Ergonomics
- [ ] Can the primary checkout / entry workflow be operated 100% via keyboard shortcuts without requiring a mouse?
- [ ] Is visual contrast high and legible in difficult lighting conditions (bright kitchens, dim dining rooms)?
- [ ] Are critical irreversible actions (cancelling a bill, resetting a database) protected by explicit confirmation modals and Manager PIN?

### 12. Errors, Telemetry & Audit Logging
- [ ] Are all financial actions, cancellations, credential changes, and system errors recorded in an immutable local audit log?
- [ ] Are sensitive customer details (passwords, complete card numbers) redacted from logs?
- [ ] Are error messages operator-friendly and actionable without exposing raw system stack traces?

### 13. API Contracts & Protocol Versioning
- [ ] Are API endpoints versioned (e.g., `/api/v1/...` or `/api/sync/state`)?
- [ ] Are request and response schemas explicitly documented and tested?
- [ ] Is backward compatibility guaranteed during staged rollout across multiple client nodes?

### 14. Automated Testing & Verification
- [ ] Does the project maintain a comprehensive test pyramid: unit tests, integration tests, concurrency benchmarks, and browser E2E tests?
- [ ] Do automated tests run on every Git commit in a clean CI pipeline?
- [ ] Are critical edge cases (kill -9 crash recovery, power loss simulation, out-of-order sync delivery) tested automatically?

### 15. Performance, Memory & Resource Budgeting
- [ ] Has maximum memory consumption been established and verified (e.g., $<250\text{ MB}$ under peak load on 4GB Windows PCs)?
- [ ] Are database queries indexed to guarantee sub-15ms latency on high-volume queries (e.g., 300,000+ historical bills)?
- [ ] Are large dataset exports streamed instead of buffering complete collections in memory?

### 16. Deployment, Downgrades & Rollbacks
- [ ] Can the application be deployed via a single, self-contained executable or automated installer?
- [ ] Is an upgrade rollback procedure documented and verified against existing customer databases?
- [ ] Are database migrations backward-compatible to allow safe binary downgrades if a release is recalled?

### 17. Operational Cost & Documentation Discipline
- [ ] Are cloud infrastructure costs minimal and budgeted (e.g., Cloudflare Workers + Durable Objects within free or standard tiers)?
- [ ] Are canonical engineering documents (`MASTER_CHECKLIST.md`, `CHANGE_LEDGER.md`, `BUG_REGISTRY.md`, `TECH_DEBT_REGISTER.md`, `ENGINEERING_PLAYBOOK.md`, `AI_HANDOVER.md`) maintained on every commit?

