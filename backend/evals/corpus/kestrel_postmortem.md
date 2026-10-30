# Incident Postmortem: Kestrel Database Failover (INC-2291)

Date of incident: September 14, 2026. Severity: SEV-1. Author: Priya Raman, Site Reliability Engineering.

## Summary

On September 14, 2026, the primary Aurora Payments database cluster, internally named Kestrel, failed to fail over automatically after the primary node lost network connectivity. Charge creation was unavailable for 47 minutes. No data was lost. Approximately 3,900 merchants experienced failed charges during the window.

## Timeline

All times are UTC.

- 14:02 — Monitoring detects elevated error rates on the charge creation endpoint.
- 14:05 — The on-call engineer, Tomas Weber, is paged and acknowledges within two minutes.
- 14:11 — The incident is declared SEV-1 and an incident channel is opened.
- 14:24 — The team determines that the automatic failover did not trigger because the health check required three consecutive failures from two witness nodes, and one witness node was itself partitioned.
- 14:41 — Manual promotion of the replica in availability zone B is initiated.
- 14:49 — The replica is promoted and charge creation recovers.
- 15:20 — The incident is closed after monitoring confirms stable error rates.

## Root cause

The failover quorum configuration assumed three witness nodes were always reachable. A network partition isolated one witness along with the primary, so the quorum could not be reached. The configuration had not been reviewed since the cluster was provisioned in 2024.

## Impact

Charge creation was down for 47 minutes, from 14:02 to 14:49 UTC. Webhook deliveries were delayed but not lost; all queued webhooks were delivered by 15:35. The customer support team received 212 tickets related to the incident.

## Action items

1. Change the failover quorum from three witnesses to a majority-of-five model. Owner: Priya Raman. Due: October 5, 2026.
2. Add an alert that fires when any witness node is unreachable for more than 60 seconds. Owner: Tomas Weber. Due: September 28, 2026.
3. Run a quarterly failover drill. Owner: SRE team. First drill scheduled for November 12, 2026.
4. Publish a status page update template for SEV-1 database incidents. Owner: Dana Okafor. Due: September 30, 2026.

## What went well

The on-call engineer acknowledged the page quickly, and the incident channel was opened within nine minutes of detection. Because writes were rejected rather than accepted by a stale primary, no data corruption occurred.
