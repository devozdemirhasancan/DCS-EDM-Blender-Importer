# DCS Argument Numbers Cheat-Sheet

DCS exposes each animatable part of an aircraft via a numeric
"argument". The importer creates one Blender action per argument, so
this list is handy when looking up which action to un-mute.

The full official list lives in each module's `Cockpit/Cockpit.lua` and
`<plane>.lua` files. The numbers below are the most common across the
core modules — your specific aircraft may extend or differ slightly.

## Common to most aircraft

| arg # | Control                              |
| :---: | ------------------------------------ |
| 0     | Aileron right                        |
| 1     | Aileron left (mirror of 0)           |
| 2     | Elevator                             |
| 3     | Rudder                               |
| 4     | Speedbrake                           |
| 5     | Flap                                 |
| 6     | Slat                                 |
| 9     | Throttle (left)                      |
| 10    | Throttle (right)                     |
| 11    | Engine RPM (left)                    |
| 12    | Engine RPM (right)                   |
| 13    | Afterburner glow (left)              |
| 14    | Afterburner glow (right)             |
| 16    | Fuel flow (left)                     |
| 17    | Fuel flow (right)                    |
| 22    | Wheel rotation (left main)           |
| 23    | Wheel rotation (right main)          |
| 24    | Wheel rotation (nose)                |
| 25    | Brake pressure                       |
| 38    | Speed brake (alternate index)        |

## Landing gear

| arg # | Control                              |
| :---: | ------------------------------------ |
| 0     | Gear down (when no aileron uses it)  |
| 6     | Gear lever                           |
| 90    | Nose strut compression               |
| 99    | Left main strut compression          |
| 101   | Right main strut compression         |

## Canopy / cockpit

| arg # | Control                              |
| :---: | ------------------------------------ |
| 38    | Canopy open/close                    |
| 39    | Cockpit lights                       |
| 192   | Pilot head movement (yaw)            |
| 193   | Pilot head movement (pitch)          |

## Weapons

| arg # | Control                              |
| :---: | ------------------------------------ |
| 100   | Hardpoint loadout flag (per pylon)   |
| 102   | Pylon visibility (depends on store)  |
| 200…300 | Per-pylon weapon visibility / sway |

## Damage arguments

Per the EDM spec, the `damage_arg` field on each render node refers to
DCS's separate "damage" argument list (200-700 range typically).
These are not exposed as actions; instead, every imported object has
an `edm_damage_arg` custom property that you can drive yourself.

## Where to find the canonical list

For any specific module, open the corresponding Lua:

```
<DCS install>\Mods\aircraft\<module>\Cockpit\Cockpit.lua
<DCS install>\Mods\aircraft\<module>\<module>.lua
```

Search for `arg = ` to find every argument the module references.

A community-maintained dump of every aircraft's argument list lives at
[hoggit/lua-mission-tools](https://github.com/hoggit/lua-mission-tools)
(URL accurate at time of writing — consult community resources for
the latest).
