# Aurora X1 - Network Setup

## Supported radios

Two point four gigahertz only, on channels one, six, and eleven. The radio does
not scan the five gigahertz band at all, and there is no ethernet or cellular
option on this hardware revision.

## Gateway requirements

One gateway serves up to sixty four sensors. Beyond that, client slots are
evicted by least-recent activity. Reserve a slot by hardware address for any
sensor whose reporting interval is longer than five minutes.

## MQTT publishing

The gateway republishes readings to MQTT under `aurora/<serial>/readings`. Set
the broker host and credentials in the gateway console, not on the sensor.
Quality of service one is the default and is the only tested setting.

## Network segmentation

Put sensors on their own VLAN. They need outbound access to the gateway only,
and blocking everything else costs nothing and removes an entire class of
exposure.
