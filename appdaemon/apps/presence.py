"""Monitors presence in the house.

Provides utility functions for other apps to check presence,
as well as the ability to register callbacks when presence changes.

User defined variables are configued in presence.yaml
"""
import uuid
from datetime import timedelta

import app


class Presence(app.App):
    """Monitor presence in the house."""

    def __init__(self, *args, **kwargs):
        """Extend with attribute definitions."""
        super().__init__(*args, **kwargs)
        self.rooms = {}
        self.last_device_date = None

    def initialize(self):
        """Create rooms with sensors and listen for new devices and people.

        Appdaemon defined init function called once ready after __init__.
        """
        super().initialize()
        self.rooms["entryway"] = Room(
            "entryway", "sensor.entryway_multisensor_motion", self
        )
        self.rooms["kitchen"] = Room(
            "kitchen", "sensor.kitchen_multisensor_motion", self
        )
        self.last_device_date = self.date()
        self.listen_event(self.handle_new_device, "device_tracker_new_device")
        self.listen_state(self.handle_presence_change, "person")

    def anyone_home(self, **kwargs) -> bool:
        """Check if anyone is home."""
        return any(
            person["state"] == "home" for person in self.get_state("person").values()
        )

    def handle_presence_change(
        self, entity: str, attribute: str, old: int, new: int, kwargs: dict
    ):  # pylint: disable=too-many-arguments
        """Change scene if everyone has left home or if someone has come back."""
        del attribute, old, kwargs
        self.log(f"{entity} is {new}")
        if new == "home":
            if "Away" in self.scene:
                self.control.reset_scene()
        elif (
            "Away" not in self.scene
            and self.get_state(
                f"person.{'rachel' if entity.endswith('dan') else 'dan'}"
            )
            != "home"
        ):
            away_scene = (
                "Day" if self.control.lights.is_lighting_sufficient() else "Night"
            )
            self.scene = f"Away ({away_scene})"

    def handle_new_device(self, event_name: str, data: dict, kwargs: dict):
        """If not home and someone adds a device, notify."""
        del event_name
        self.log(f"New device added: {data}, {kwargs}")
        if "Away" in self.scene:
            if self.last_device_date < self.date() - timedelta(hours=3):
                self.notify(
                    f'A guest has added a device: "{data["host_name"]}"',
                    title="Guest Device",
                )
                self.last_device_date = self.date()


class Room:
    """Report on presence for an individual room."""

    def __init__(self, room_id: str, sensor_id: str, controller: Presence):
        """Initialise with attributes for light parameters, and a Light controller."""
        self.room_id = room_id
        self.controller = controller
        vacant = self.controller.get_state(sensor_id) == 0
        self.last_entered = self.controller.datetime() - timedelta(
            seconds=15 if vacant else 0
        )
        self.last_vacated = self.controller.datetime() - timedelta(
            seconds=15 if not vacant else 0
        )
        self.callbacks = {}
        self.controller.listen_state(self.handle_presence_change, sensor_id, old="0")
        self.controller.listen_state(self.handle_presence_change, sensor_id, new="0")

    @property
    def is_vacant(self) -> bool:
        """Check if vacant based on last time vacated and entered."""
        return self.last_vacated > self.last_entered

    def time_in_room(self) -> timedelta:
        """Time in room - negative value represents time since last left."""
        return (
            self.last_vacated - self.controller.datetime()
            if self.is_vacant
            else self.controller.datetime() - self.last_entered
        )

    def handle_presence_change(
        self, entity: str, attribute: str, old: int, new: int, kwargs: dict
    ):  # pylint: disable=too-many-arguments
        """If room presence changes, trigger all registered callbacks."""
        del entity, attribute, old, kwargs
        new = float(new)
        self.controller.log(
            f"The {self.room_id} is now {'vacant' if new == 0 else 'occupied'}",
            level="DEBUG",
        )
        self.last_vacated = self.controller.datetime()
        for callback in self.callbacks.values():
            if callback.get("timer_handle") is not None:
                self.controller.cancel_timer(callback["timer_handle"])
            if new != 0 or callback["vacating_delay"] == 0:
                callback["callback"](is_vacant=new == 0)
                self.controller.log(f"Called callback: {callback}", level="DEBUG")
            else:
                callback["timer_handle"] = self.controller.run_in(
                    callback["callback"], callback["vacating_delay"], is_vacant=True
                )
                self.controller.log(
                    f"Set vacation timer for callback: {callback}", level="DEBUG"
                )

    def register_callback(self, callback, vacating_delay: int = 0) -> uuid.UUID:
        """Register a callback for when presence changes, including an optional delay."""
        handle = uuid.uuid4().hex
        self.callbacks[handle] = {
            "callback": callback,
            "vacating_delay": vacating_delay,
        }
        self.controller.log(f"Registered callback: {callback}", level="DEBUG")
        return handle

    def cancel_callback(self, handle):
        """Cancel a callback (and its timer if it has one) by passing its handle."""
        if self.callbacks[handle].get("timer_handle") is not None:
            self.controller.cancel_timer(self.callbacks[handle]["timer_handle"])
        del self.callbacks[handle]
