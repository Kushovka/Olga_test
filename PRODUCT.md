# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Delegated by the user: FastAPI, PostgreSQL, Docker Compose and vanilla HTML/CSS/JavaScript.

## Users

Gamers buying digital products such as game keys, subscriptions, gift cards and Steam top-ups.

## Product Purpose

Demonstrate a digital-goods storefront and, principally, safe one-time delivery after payment under retries, concurrent webhooks and provider failures.

## Capabilities and Constraints

The assignment requires the storefront's upper section, five specified interactions, an emulated payment webhook, an order-status page, race tests, recovery states, two configurable supplier stubs and concurrency-safe promotional codes. No real payment gateway, complete mobile version or production authentication is required.

## Evidence on Hand

The supplied assignment document and Figma file are the source of truth. Product names and prices below are synthetic test data from the assignment; no commercial claims are made.

## Product Principles

- A paid order receives at most one delivery code.
- Incoming payment events are durable and idempotent.
- A timeout is ambiguous, so retries reuse the same supplier request id.
- Recovery must be explicit, observable and safe to retry.
