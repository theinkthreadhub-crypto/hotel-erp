# HoReCa One — Safe Legacy Bootstrap & Baseline Migration Architecture

**Phase:** Phase 3.1 Architecture Specification  
**Document:** `docs/sqlite-phase2b/Safe-Legacy-Bootstrap.md`  
**Status:** Approved for implementation in subsequent phases (No live migration executed in Phase 3.1)

---

## 1. Executive Summary

In legacy versions (prior to Phase 3.0), the counter PC stored sync outbox entries as summary-only metadata:
```json
{
  "seq": 1024,
  "ref": "b_1730000000000_1234",
  "detail": "Bill #45 printed",
  "sent_at": null
}
```
Such records contain no transaction payload, item details, payment allocations, or ledger adjustments. They are completely insufficient for reconstructing financial history on the cloud.

Phase 3.0 established durable, immutable operation envelopes with SHA-256 integrity checksums and full business mutations. Phase 3.1 implemented authenticated relational cloud ingestion (`POST /api/sync/ops`).

This document defines the protocol for transitioning an existing hotel database with legacy outbox rows to the Phase 3.1 relational cloud without data loss, downtime, or duplicate financial effects.

---

## 2. Core Safety Principles

1. **Never False-Ack Legacy Rows:**  
   Legacy summary-only rows in `sync_outbox` MUST NEVER be marked acknowledged (`sent_at = NOW()`) simply because a baseline snapshot transfer was attempted.
2. **Atomic Frozen Checkpoint:**  
   The baseline snapshot must be captured from a frozen read view (e.g. SQLite WAL read transaction or cloned snapshot) at a discrete version (`base_version`).
3. **Continuous Concurrent Ingestion:**  
   Local business operations must never be blocked during baseline transfer. While the baseline snapshot transfers historical data, new local sales, KOTs, and vouchers generate standard Phase 3.0 envelopes with `doc_version > base_version` into the outbox.
4. **Partitioned Bounded Batches:**  
   Large databases (e.g., 50,000 bills, 200,000 items) must be transferred in bounded partitions (100–250 records per HTTP batch) to stay well within Cloudflare Worker 128 MB RAM and 50 ms CPU limits.
5. **Two-Phase Financial Reconciliation:**  
   Baseline completion requires deterministic financial balance matching:
   - Total bill count
   - Total gross, net, tax, and discount sums
   - Total voucher credit/debit balances
   - Stock balance checksums  
   Only when cloud and local checksums match 100% is the legacy baseline marked reconciled.

---

## 3. The 5-Step Baseline Transfer Protocol

### Step 1: Frozen Source Checkpoint Creation
1. Open a local read transaction on the SQLite database:
   ```sql
   BEGIN DEFERRED TRANSACTION;
   ```
2. Read the current version: `checkpoint_version = meta('version')`.
3. Read the highest legacy sequence: `legacy_seq_max = SELECT MAX(seq) FROM sync_outbox WHERE is_legacy_outbox = 1`.
4. Release read lock immediately or stream directly from WAL snapshot.

### Step 2: Bounded Partition Extraction & Envelope Synthesis
For historical records created before `checkpoint_version`:
1. Extract records in pages of 100:
   - Bills with joined items and payments
   - Vouchers and transactions
   - Stock items and ledger movements
   - Active tables and KOTs
2. Package each partition as an incremental Phase 3.0 synthetic baseline envelope:
   - `op_id = "baseline_" + hotel_id + "_" + entity + "_" + page_index`
   - `doc_version = checkpoint_version`
   - `event_type = "baseline_sync"`
   - `integrity.checksum = sha256(canonicalJson(payload))`
3. Dispatch via `POST /api/sync/ops`.

### Step 3: Cloud Relational Ingestion & Deduplication
1. Cloud receives synthetic baseline envelopes at `POST /api/sync/ops`.
2. Each envelope is validated against hotel credentials and checksum.
3. Records are upserted into `sync_bills`, `sync_bill_items`, `sync_bill_payments`, `sync_vouchers`, etc.
4. Duplicate baseline deliveries are recognized idempotently by `op_id` and return cached committed acknowledgments.

### Step 4: Full Financial Reconciliation
Once all partitions for `checkpoint_version` are ingested:
1. Local agent runs reconciliation query:
   ```sql
   SELECT COUNT(*), SUM(total), SUM(tax), SUM(sub) FROM bills;
   SELECT COUNT(*), SUM(amount) FROM vouchers;
   ```
2. Remote cloud DO executes identical relational aggregation:
   ```sql
   SELECT COUNT(*), SUM(total), SUM(tax), SUM(sub) FROM sync_bills;
   SELECT COUNT(*), SUM(amount) FROM sync_vouchers;
   ```
3. If aggregations match:
   - Checkpoint `cloud_baseline_reconciled` is recorded locally and remotely.
   - Proceed to Step 5.
4. If aggregations do not match:
   - Quarantine discrepancy; baseline is NOT certified; alert manager; retry missing partitions.

### Step 5: Safe Retirement of Legacy Outbox Rows
Only after Step 4 certifies 100% reconciliation:
1. Legacy summary-only rows in `sync_outbox` where `seq <= legacy_seq_max` are marked:
   ```sql
   UPDATE sync_outbox 
   SET sent_at = ? 
   WHERE seq <= ? AND (envelope IS NULL OR json_extract(detail, '$.envelope_version') IS NULL);
   ```
2. An audit event is recorded: `Legacy sync_outbox retired up to seq <legacy_seq_max> with verified baseline reconciliation`.

---

## 4. Safety Guardrails Summary

| Condition | Failure Action | Guardrail |
| :--- | :--- | :--- |
| Network drop during baseline batch | Worker halts batch | Next retry re-sends un-acknowledged batch; DO is idempotent. |
| Client crash during baseline | Process resumes from last acked page | No partial-batch corruption; transactions atomic in SQLite. |
| Sale committed while baseline uploading | Normal Phase 3.0 envelope created | Outbox retains new envelope; dispatched after or concurrent with baseline. |
| Reconciliation checksum mismatch | Baseline marked FAILED | Legacy outbox rows NEVER acknowledged; manual review triggered. |
| Monolithic JSON write attempt | Rejected by architecture | `POST /api/sync/ops` writes solely to relational tables; `chunk` slot `cur` untouched. |
