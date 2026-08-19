# Aurora X1 - Local HTTP API

Every unit serves a small read-only HTTP API on port 8080 while it is awake. The
API is unauthenticated on the local link and is intended for diagnostics and for
exporting data before service.

## GET /api/v1/status

Returns firmware version, uptime in seconds, battery percentage, and the current
network state. Use it to confirm the unit is awake before any other call.

## GET /api/v1/readings

Returns the most recent one thousand readings as JSON. Supports a `since` query
parameter carrying a Unix timestamp.

## GET /api/v1/buffer/export

Exports the complete logging buffer as a gzipped NDJSON stream. This is the only
supported way to export the logging buffer, and it is the export a warranty
claim requires. Run this export before any procedure that clears storage, since
nothing recovers the buffer afterwards.

## POST /api/v1/calibrate

Starts the calibration routine remotely. Returns 409 while a calibration is
already running.
