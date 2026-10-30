# Aurora Payments API — Developer Guide

Aurora is the payments platform built by Vantora Systems. This guide covers authentication, rate limits, webhooks, and error handling for API version 4.

## Authentication

Every request must carry an API key in the `X-Aurora-Key` header. Keys beginning with `ak_test_` operate on the sandbox; keys beginning with `ak_live_` operate on production. Keys expire after 90 days and must be rotated from the Developer Console. Aurora does not support OAuth 2.0 client credentials in version 4; OAuth support is planned for version 5.

The base URL for production is `https://api.aurora.vantora.example/v4`. The sandbox base URL is `https://sandbox.aurora.vantora.example/v4`.

## Rate limits

Rate limits are enforced per API key, per minute.

| Plan | Requests per minute | Burst allowance |
|---|---|---|
| Free | 60 | 10 |
| Pro | 600 | 100 |
| Enterprise | 6000 | 1500 |

When a limit is exceeded Aurora returns HTTP 429 with a `Retry-After` header expressed in seconds. Clients should use exponential backoff starting at 2 seconds. The webhook delivery endpoint is not subject to these limits.

## Idempotency

POST requests that create charges accept an `Idempotency-Key` header. Aurora stores idempotency keys for 24 hours. Replaying a request with the same key within that window returns the original response without creating a second charge. Keys longer than 255 characters are rejected with error code `invalid_idempotency_key`.

## Webhooks

Aurora signs every webhook with HMAC-SHA256 using the endpoint secret. The signature is delivered in the `Aurora-Signature` header. Failed deliveries are retried up to 8 times over 3 days with exponential backoff. After the eighth failure the endpoint is automatically disabled and the account owner receives an email.

Supported webhook events are: `charge.succeeded`, `charge.failed`, `refund.created`, `dispute.opened`, and `payout.paid`. Subscription events are not available in version 4.

## Error codes

| Code | HTTP status | Meaning |
|---|---|---|
| `card_declined` | 402 | The issuing bank declined the card. |
| `insufficient_funds` | 402 | The card has insufficient funds. |
| `invalid_idempotency_key` | 400 | The idempotency key exceeds 255 characters. |
| `key_expired` | 401 | The API key is older than 90 days. |
| `rate_limited` | 429 | The per-minute limit was exceeded. |
| `region_unsupported` | 422 | The charge currency is not available in the merchant's region. |

## Currencies and regions

Aurora can settle in USD, EUR, GBP, CAD, and AUD. Settlement in JPY and INR is not available. Merchants in Brazil and Mexico can accept charges but must settle in USD.

## Refunds

Refunds can be issued for up to 180 days after the original charge. A partial refund can be issued multiple times as long as the total does not exceed the original amount. Refunds to cards typically take 5 to 10 business days to appear on the customer's statement.

## SDKs

Official SDKs exist for Python, Node.js, Go, and Ruby. There is no official Java or PHP SDK; community libraries exist but are not supported by Vantora.
