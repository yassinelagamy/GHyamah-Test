# Postmortem: Repeated OOMKilled Container Restarts

**Severity:** SEV-2  
**Incident date:** 2026-07-24  
**Duration:** 45 minutes (14:05–14:50 EEST)  
**Status:** Resolved

## 1. Summary

On 2026-07-24, the application was unavailable for 45 minutes after its containers entered a repeated `OOMKilled` crash loop with exit code 137. Memory usage had grown gradually following a release that introduced an unbounded in-process cache; once each container reached its configured memory limit, the container runtime terminated it. Automated client retries and queued traffic increased load on the briefly recovering containers, accelerating subsequent failures. Users experienced an estimated 95–100% request error rate during the incident, amounting to effective full downtime. The incident was classified as **SEV-2** because the production service was unavailable, but no data loss or security impact was identified.

## 2. Timeline

All times are EEST (UTC+3).

| Time | Event | Actor/action |
|---|---|---|
| 13:40 | Release `v2.18.0` is deployed. It contains a new in-process response cache. | Deployment pipeline completes successfully; smoke checks pass. |
| 13:45 | Memory begins rising above the previous baseline of approximately 55% per container. | Application traffic populates the cache; no alert exists for sustained memory growth. |
| 13:52 | Memory reaches approximately 75% and continues to grow without returning to baseline. | No action is taken because memory-usage alerting is not configured. |
| 14:03 | One container approaches its configured memory limit; garbage collection activity and latency increase. | Container continues serving requests with degraded response times. |
| 14:05 | First container is terminated by the runtime as `OOMKilled` with exit code 137. | Runtime restart policy starts a replacement container; incident begins (minute 0). |
| 14:07 | The replacement becomes ready, receives queued and retried requests, and its cache grows rapidly. | Client retries and redistributed traffic increase pressure on the remaining containers. |
| 14:10 | Multiple containers enter a restart loop; error rate exceeds 95%. | Runtime repeatedly restarts terminated containers, but they fail again after becoming ready. |
| 14:13 | Availability alert fires after sustained health-check failures. | On-call engineer is paged and acknowledges the alert. |
| 14:16 | On-call confirms widespread HTTP 5xx/timeouts and repeated container restarts. | Engineer begins incident triage and declares SEV-2. |
| 14:20 | Exit code 137 and `OOMKilled` events are identified; memory graphs show steady growth after the release. | Engineer correlates the failure pattern with deployment `v2.18.0`. |
| 14:24 | Incident lead pauses nonessential changes and selects rollback as the primary mitigation. | A second engineer reviews the previous stable image and rollback procedure. |
| 14:28 | Memory limits are temporarily raised to provide recovery headroom while rollback proceeds. | Platform operator updates the workload configuration and replaces affected containers. |
| 14:33 | Rollback to `v2.17.4` starts. | Deployment pipeline replaces the leaking release with the last known-good image. |
| 14:38 | First rolled-back containers become healthy; error rate begins to fall. | On-call watches health checks, memory, restarts, latency, and request errors. |
| 14:42 | All active containers run `v2.17.4`; memory stabilizes near the prior baseline. | Traffic is allowed to normalize; retry pressure subsides. |
| 14:47 | Health checks remain successful and no new OOM kills occur for five minutes. | Incident lead begins the recovery validation period. |
| 14:50 | Error rate and latency return to normal; full service is confirmed. | Incident lead resolves the incident after 45 minutes of effective downtime. |

## 3. Root Cause

### 5-Whys analysis

1. **Why was the application unavailable?**  
   Its production containers repeatedly terminated and restarted, leaving insufficient healthy capacity to serve requests.

2. **Why did the containers terminate?**  
   Each container exceeded its memory limit and was killed by the container runtime, producing an `OOMKilled` event and exit code 137.

3. **Why did memory exceed the limit?**  
   Release `v2.18.0` introduced an unbounded in-process response cache. Cache entries were not evicted, so memory grew continuously with request diversity.

4. **Why did the release cause a crash loop rather than degrade safely?**  
   The memory limit was sized for the old application baseline and did not include sufficient headroom for the new allocation pattern. Restarted instances were also immediately exposed to queued and retried traffic, causing the cache to refill quickly.

5. **Why was the defect not detected before or shortly after deployment?**  
   CI did not include memory-regression soak or load testing, and production monitoring did not alert on sustained memory utilization, abnormal restart count, or `OOMKilled` events.

**Root cause:** A memory leak introduced in `v2.18.0`—an unbounded in-process cache—caused container memory to grow until it exceeded a limit sized for the previous baseline. The impact was compounded by retry traffic, insufficient memory headroom, absent memory and restart alerting, and the lack of memory-regression testing in CI.

## 4. Recommendations

| Action | Owner (role) | Priority |
|---|---|---|
| Replace the unbounded cache with a size- and TTL-bounded implementation; add eviction metrics and tests. | Application engineering lead | P0 |
| Recalculate container memory requests/limits from measured peak usage and retain operational headroom. | Platform/SRE engineer | P0 |
| Alert when per-container memory utilization exceeds 80% for five minutes. | Observability/SRE engineer | P0 |
| Alert when a workload records more than three restarts in ten minutes, and surface `OOMKilled`/exit-code-137 events. | Observability/SRE engineer | P0 |
| Implement the proposed horizontal auto-scaling policy below after load validation. | Platform/SRE engineer | P1 |
| Add sustained soak/load tests and memory-regression thresholds to CI before production promotion. | Quality engineering and application teams | P1 |
| Write and exercise an OOM/crash-loop response runbook covering diagnosis, rollback, temporary headroom, and retry control. | Incident management/SRE lead | P1 |
| Add bounded exponential backoff and jitter to applicable client and internal retries. | Application engineering team | P2 |

## 5. Proposed Auto-scaling Policy for Ghaymah

This is a proposed policy design for workloads deployed on Ghaymah; it does not assume a named or currently documented Ghaymah autoscaling feature.

```yaml
policy_name: production-api-resource-scaling
mode: horizontal
replicas:
  minimum: 2
  maximum: 10  # N; validate against load tests, quota, and downstream capacity
scale_out:
  evaluation_window: 2m
  conditions:
    operator: OR
    rules:
      - metric: average_container_memory_utilization
        threshold: "> 70%"
      - metric: average_container_cpu_utilization
        threshold: "> 65%"
  increment:
    strategy: proportional
    minimum_replicas: 1
    maximum_step_percent: 50
scale_in:
  memory_threshold: "< 45%"
  cpu_threshold: "< 40%"
  evaluation_window: 10m
  condition_operator: AND
  decrement: 1
  cooldown: 10m
stabilization:
  scale_out_cooldown: 2m
  scale_in_cooldown: 10m
```

The maximum `N` is initially **10 replicas** and must be validated against measured container throughput, account capacity, and the limits of databases and other downstream services. Scale-out occurs when either average memory exceeds 70% or average CPU exceeds 65% for two continuous minutes. Scale-in requires both metrics to remain low and uses a 10-minute cooldown—within the requested 5–10 minute range—to prevent flapping. At least two replicas remain active for availability.

Autoscaling alone does **not** fix a memory leak: every new replica runs the same defective code and will eventually leak. Horizontal scaling buys response time, preserves capacity during a gradual rise, and absorbs the retry storm while engineers mitigate the defect. It should be complemented by a properly measured memory limit with vertical headroom, bounded retries, readiness checks, and a restart policy that replaces failed containers without creating an uncontrolled hot loop. The lasting corrective action is to remove the leak.

## 6. Early Detection with a Monitoring Approach on Ghaymah

Because Ghaymah's public documentation does not establish specific monitoring, alerting, or autoscaling product features, the following approach uses platform-agnostic container signals. These signals can be collected from container runtime statistics and events, combined with an external monitor that calls the application's `/health` endpoint.

### Signals and patterns

- Plot per-container memory working set and memory utilization against the configured limit. A steady creep after a deployment, or a repeating sawtooth pattern that rises to the limit and drops when a container restarts, is an early indicator of a leak or crash loop.
- Track container restart count and restart rate by workload, release version, and container instance.
- Capture termination reason, especially `OOMKilled`, and exit code 137.
- Monitor `/health` availability and latency externally so an alert remains effective even when the application or container-level telemetry is unavailable.
- Correlate memory, restarts, HTTP error rate, latency, and deployments on the same operational dashboard.

### Alert rules

| Signal | Proposed rule | Purpose |
|---|---|---|
| Memory utilization | Per-container memory > 80% of limit for 5 minutes | Warn before the runtime enforces the limit. |
| Restart count | More than 3 restarts for the same workload in 10 minutes | Detect a crash loop early. |
| OOM event | Any `OOMKilled` event or exit code 137 in production | Page immediately on confirmed memory exhaustion. |
| Health availability | Two or more consecutive `/health` failures from an external monitor | Detect loss of service independently of container telemetry. |
| Memory growth | Sustained positive memory slope after a release, with no return toward baseline | Identify slow leaks before the hard threshold is reached. |

Operational dashboards should show the current release version alongside memory utilization, limit, restart count, termination reason, health status, latency, and error rate. Alerts should route to the on-call notification channel with the workload, container, release, current memory percentage, restart count, and a link to the OOM runbook.

The authenticated application page reviewed for this assessment exposes deployment status and application logs, but no documented configurable memory/restart alert controls were established. The implementation should therefore export container runtime metrics and events to an external monitoring system and retain an external `/health` probe unless Ghaymah support enables equivalent account-level controls.
