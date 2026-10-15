# Capacity on Cloudflare FREE plan — goal: 100 libraries × 100 students

**Verdict (measured with `node cloud/smoke.js --load`, 100 libraries × 100 students on local D1): fits the free plan.** The tightest limit is **Worker requests/day (100 000)**: ~78 % used in a busy-day model. D1 writes ~66 % used. Storage ~7 % used.

## Cloudflare free limits used (check dashboard — they can change)
| Limit | Free plan | Our model (100 libs × 100 students) | Used |
|---|---|---|---|
| Worker requests / day | 100 000 | ≈ 78 000 | 78 % |
| D1 rows written / day | 100 000 | ≈ 66 000 | 66 % |
| D1 rows read / day | 5 000 000 | ≈ 0.8 M | 16 % |
| D1 storage | 5 GB | ≈ 0.4 GB (30 daily backups each) | 8 % |
| Worker CPU / request | 10 ms | small work per call (single-row reads; no big JSON parse) | — |

## Busy-day model (per library, ERP open 12 h, 100 students all active)
| Source | Requests | Rows written |
|---|---|---|
| ERP poll every 3 min | 240 | 0 |
| ERP pushes (40/day, debounced 9 s) | 40 | 40 × 7 = 280 |
| Students: 2 opens + IN + OUT each | 500 | IN + OUT + ack-delete ≈ 300 |
| Day-roll student rows (attendance string grows) | — | ≈ 70 |
| **Total / library / day** | **≈ 780** | **≈ 660** |
| **× 100 libraries** | **≈ 78 000** | **≈ 66 000** |

Browser caching (student page 10 min, manifest/icons 1 h) keeps static fetches out of the request count.

## Measured per-call cost (local D1, 100 libs × 100 students)
| Call | rows written | rows read | latency p50 / p95 |
|---|---|---|---|
| `/api/push` | 7 | 18 | server work only; client builds payload |
| `/api/poll` | 0 | 9 | 41 / 83 ms |
| `/api/student` (read) | 0 | 13 | 58 / 99 ms |
| `/api/student-mark` | ~1 | 13 | 58 / 99 ms |
Before v1.26: push = 10 writes / 486 reads; whole student list rewritten and parsed on every student open (400 KB JSON).

## Data sizes (100 students, one session)
| Item | Before | Now |
|---|---|---|
| Cloud backup per day (base64 gzip) | 130 KB | **~100 KB** (att packed) |
| Student data in cloud | 1 blob 403 KB (rewritten every push) | **100 rows × 2.4 KB** (only changed rows written) |
| Push payload (typical edit) | ~530 KB | **~100 KB backup + ~3 KB** |
| Student page load | parse 400 KB | read 1 row (≈ 2.4 KB) |

## When you will outgrow the free plan
| Trigger | Do this |
|---|---|
| Requests/day > ~85 000 | poll 3 → 5 min (`180e3` → `300e3` in server.js / mobile.js) — saves ~96 requests/lib; or go Workers Paid |
| D1 writes/day > ~85 000 | raise ERP debounce 9 s → 20 s; cut `KEEP_DAYS` 30 → 14; or Workers Paid |
| > 100 libraries | **Workers Paid ($5/month)**: 10 M requests/month, 50 M rows written/month, 5 GB+ — cheapest fix, do this before you hit limits |
| One library > 500 students | its backup row nears the 1.9 MB cap (`sizeWarn` flag in push reply); archive old sessions |

## How to re-run the test
```
cd library-erp
node cloud/smoke.js           # 38 functional checks (needs npx wrangler; ~1 min)
node cloud/smoke.js --load    # + 100 libraries × 100 students, prints rows written/read per endpoint
```
