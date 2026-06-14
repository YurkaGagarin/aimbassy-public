# Day-5 guardrail mini-eval (confusion matrix) · 2026-06-10

Labeled synthetic messages: 40. Gate = binary classifier; positive = the risk to catch.
Recall is the safety-critical metric (a missed risk is worse than a false alarm).

## topic (positive = OFF-topic)

| | pred + | pred - |
|---|---|---|
| **actual +** | TP 19 | FN 0 |
| **actual -** | FP 0 | TN 21 |

Accuracy 1.00 · Precision 1.00 · Recall 1.00 · F1 1.00
Misclassified: none

## injection (positive = injection)

| | pred + | pred - |
|---|---|---|
| **actual +** | TP 8 | FN 0 |
| **actual -** | FP 0 | TN 32 |

Accuracy 1.00 · Precision 1.00 · Recall 1.00 · F1 1.00
Misclassified: none

## pii (positive = PII present)

| | pred + | pred - |
|---|---|---|
| **actual +** | TP 10 | FN 0 |
| **actual -** | FP 2 | TN 28 |

Accuracy 0.95 · Precision 0.83 · Recall 1.00 · F1 0.91
Misclassified: g22(FP), g33(FP)

