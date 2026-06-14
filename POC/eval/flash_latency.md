# Lever 3 latency: generator Pro vs Flash on identical RRF+rerank hits

Retrieval held constant (RRF + Flash rerank, frozen DE rewrite). Generator only varies. n=13. Wall-clock of the generate() HTTP call (temperature 0.2, maxOutputTokens 8192).

Mean generate latency: Pro 23.8s -> Flash 12.5s (-11.3s, -47%)

| id | in-corpus | difficulty | pro s | flash s | speedup |
|---|---|---|---|---|---|
| q01 | no | difficult | 20.4 | 4.4 | 4.7x |
| q02 | no | easy | 23.9 | 8.3 | 2.9x |
| q03 | yes | easy | 21.6 | 8.0 | 2.7x |
| q04 | yes | easy | 23.7 | 20.1 | 1.2x |
| q05 | no | difficult | 26.0 | 14.5 | 1.8x |
| q06 | no | difficult | 26.3 | 10.2 | 2.6x |
| q07 | yes | difficult | 25.6 | 14.5 | 1.8x |
| q08 | no | difficult | 25.4 | 13.4 | 1.9x |
| q09 | yes | easy | 21.2 | 14.9 | 1.4x |
| q10 | yes | easy | 24.9 | 10.7 | 2.3x |
| q11 | no | difficult | 22.2 | 17.6 | 1.3x |
| q12 | yes | easy | 23.1 | 14.9 | 1.5x |
| q13 | yes | difficult | 25.2 | 11.0 | 2.3x |
