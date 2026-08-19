# Aurora X1 - Troubleshooting

## Readings drift upward over several days

Almost always a calibration problem rather than a hardware fault. Confirm the
ambient temperature has not shifted more than five degrees since the last
calibration, then recalibrate. If the drift returns within a week, the sensing
element is failing and the unit needs replacement.

## The unit drops off the network every few hours

Check gateway client slots first. A gateway at capacity evicts the least active
client, and a sensor reporting every five minutes is often the least active
thing on the network. Raise the reporting frequency, or reserve a slot by
hardware address.

## Pairing fails after a factory reset

Pairing mode times out after two minutes. Hold the pairing pin for five seconds
to re-enter it, and keep the unit within two metres of the gateway. A unit that
refuses three consecutive pairing attempts has a damaged pairing pin.

## Firmware update fails partway

The unit keeps the previous firmware and rolls back automatically, so a failed
update is not fatal. Retry on mains power; updates below twenty percent battery
are refused outright.
