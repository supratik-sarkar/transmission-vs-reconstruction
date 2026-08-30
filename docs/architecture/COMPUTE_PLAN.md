# Compute plan

## MacBook Pro M4 Pro

Use as the default coordinator when the relay/receiver are remote APIs. It is sufficient for:

- source processing;
- deterministic protocol tests;
- API orchestration;
- bootstrapping/statistics;
- tables/plots;
- small local-model MPS checks.

## Colab Pro A100

Use when the experiment requires open-weight CUDA inference or high-throughput local sampling. The GPU does not materially accelerate remote API latency.

## Reproducibility

A provider/model run is not reproducible merely because `temperature=0`. Exact model/revision strings and an operational repeatability audit are required by the protocol.
