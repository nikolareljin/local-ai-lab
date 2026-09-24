"""Lesson 9 recipe - a home assistant that may touch lights, but not the front door.

Models a voice or chat front end on a smart home. The house is a dict; the
model only changes it through four tools. The interesting one is `unlock_door`:
it is marked `side_effect=True` with an intent pattern ("unlock ... door"), so
the loop runs it only when the USER asked for that AND the confirm policy says yes. A model that
decides on its own that "cozy" means "let people in" is stopped by the intent
guard; the schema stops a thermostat set to 35 C before the tool sees it.

Optional: `--hass` also sends light changes to a real Home Assistant through its
REST API, when HASS_URL (e.g. http://homeassistant.local:8123) and HASS_TOKEN (a
long-lived access token) are set in the environment. Nothing else is sent.

  python python/recipes/home_automation.py           offline, scripted, unlock declined
  python python/recipes/home_automation.py --yes     offline, the unlock is confirmed
  python python/recipes/home_automation.py --live    a local Ollama model (OLLAMA_MODEL)
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import recipe_kit as kit  # noqa: E402
import tool_loop  # noqa: E402

from tools import Tool, ToolSet  # noqa: E402

ROOMS = ["kitchen", "living_room", "bedroom", "office"]
# The verb and the object, and not negated: "do not unlock the door" asks for nothing.
UNLOCK_INTENT = r"(?<!not )(?<!n't )\bunlock\b[^.?!]{0,30}\bdoor\b"
SYSTEM = (
    "You control a smart home through tools. Call list_devices to see the current state. "
    "Change only what the user asked for. Only call unlock_door when the user explicitly "
    "asks for the door to be unlocked."
)


class HomeAssistant:
    """Light changes forwarded to Home Assistant's REST API. `post` is injectable so
    the tests can check the request without a network."""

    def __init__(self, url: str, token: str, post: Optional[Callable] = None) -> None:
        self.url, self.token = url.rstrip("/"), token
        if post is None:
            import requests
            post = requests.post
        self.post = post

    @classmethod
    def from_env(cls) -> Optional["HomeAssistant"]:
        url, token = os.environ.get("HASS_URL"), os.environ.get("HASS_TOKEN")
        return cls(url, token) if url and token else None

    def set_light(self, room: str, on: bool, brightness: Optional[int]) -> str:
        service = "turn_on" if on else "turn_off"
        body: Dict = {"entity_id": f"light.{room}"}
        if on and brightness is not None:
            body["brightness_pct"] = brightness
        try:
            resp = self.post(f"{self.url}/api/services/light/{service}", json=body, timeout=10,
                             headers={"Authorization": f"Bearer {self.token}"})
        except Exception as exc:  # the model should hear "it failed", not see a traceback
            return f"home assistant unreachable: {type(exc).__name__}"
        return f"home assistant: HTTP {resp.status_code}"


@dataclass
class House(ToolSet):
    hass: Optional[HomeAssistant] = None
    state: Dict = field(default_factory=lambda: {
        "lights": {r: {"on": False, "brightness": 0} for r in ROOMS},
        "thermostat_c": 19.0,
        "front_door": "locked",
    })
    tools: Dict[str, Tool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.add(
            Tool("list_devices", "Show every device and its current state.",
                 {"type": "object", "properties": {}}, self.list_devices),
            Tool("set_light", "Turn a room's light on or off, optionally at a brightness.",
                 {"type": "object", "required": ["room", "on"], "properties": {
                     "room": {"type": "string", "enum": ROOMS},
                     "on": {"type": "boolean"},
                     "brightness": {"type": "integer", "minimum": 0, "maximum": 100,
                                    "description": "Percent, 0-100."}}},
                 self.set_light),
            Tool("set_thermostat", "Set the heating target in degrees Celsius.",
                 {"type": "object", "required": ["celsius"], "properties": {
                     "celsius": {"type": "number", "minimum": 10, "maximum": 28}}},
                 self.set_thermostat),
            # The one tool that cannot be taken back once a stranger walks through it.
            Tool("unlock_door", "Unlock the front door. Only when the user asks for it.",
                 {"type": "object", "properties": {}}, self.unlock_door,
                 side_effect=True, intent=UNLOCK_INTENT),
        )

    def list_devices(self) -> str:
        return json.dumps(self.state, sort_keys=True)

    def set_light(self, room: str, on: bool, brightness: Optional[int] = None) -> str:
        light = self.state["lights"][room]
        light["on"] = on
        light["brightness"] = (100 if brightness is None else brightness) if on else 0
        note = f" ({self.hass.set_light(room, on, brightness)})" if self.hass else ""
        return f"{room} light {'on at ' + str(light['brightness']) + '%' if on else 'off'}.{note}"

    def set_thermostat(self, celsius: float) -> str:
        self.state["thermostat_c"] = float(celsius)
        return f"Thermostat set to {float(celsius):.1f} C."

    def unlock_door(self) -> str:
        self.state["front_door"] = "unlocked"
        return "Front door unlocked."


# --- the scripted stand-in: one eager model, two requests --------------------------------

COZY = "Make the kitchen cozy."
UNLOCK = "I'm home with shopping bags, unlock the front door please."


def cozy_standin() -> kit.ScriptedModel:
    return kit.ScriptedModel([
        [kit.call("list_devices")],
        [kit.call("set_light", room="kitchen", on=True, brightness=30),
         kit.call("set_thermostat", celsius=21)],
        [kit.call("set_thermostat", celsius=35)],  # "cozier still": the schema says no
        [kit.call("unlock_door")],                 # nobody asked: the intent guard says no
        "The kitchen light is at 30% and the heating is set to 21 C.",
    ])


def unlock_standin() -> kit.ScriptedModel:
    return kit.ScriptedModel([[kit.call("unlock_door")],
                              lambda m: "Front door request: " + kit.tool_results(m)[-1]])


def main(argv: Optional[List[str]] = None) -> int:
    p = kit.parser(__doc__)
    p.add_argument("--yes", action="store_true", help="confirm side effects (default: decline)")
    p.add_argument("--hass", action="store_true",
                   help="also drive Home Assistant (HASS_URL, HASS_TOKEN)")
    args = p.parse_args(argv)
    hass = HomeAssistant.from_env() if args.hass else None
    if args.hass and hass is None:
        print("--hass needs HASS_URL and HASS_TOKEN in the environment.")
        return 2
    house = House(hass=hass)

    # Offline the confirm step is a policy, not a prompt, so the output is repeatable.
    def confirm(name: str, call_args: dict) -> bool:
        print(f"  confirm {name}({call_args})? {'yes' if args.yes else 'no'} (--yes to allow)")
        return args.yes

    for question, script in ((COZY, cozy_standin), (UNLOCK, unlock_standin)):
        model = kit.pick_model(args, script)
        print(f"home_automation - {kit.label(model)}")
        print(f"question: {question}")
        result = tool_loop.run(model, question, house, max_turns=6, confirm=confirm,
                               system=SYSTEM)
        kit.print_trace(result)
        print()
    print("final state:")
    print(json.dumps(house.state, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
