"""Monitors media devices.

Monitors the TV to change the scene appropriately.

User defined variables are configued in media.yaml
"""

import subprocess
import app


class Media(app.App):
    """Listen for TV state changes to set the scene appropriately."""

    def __init__(self, *args, **kwargs):
        """Extend with attribute definitions."""
        super().__init__(*args, **kwargs)
        self.__entity_id = "media_player.tv"
        self.__last_source = None

    def initialize(self):
        """Start listening to TV states.

        Appdaemon defined init function called once ready after __init__.
        """
        super().initialize()
        self.__last_source = self.get_state(self.__entity_id, attribute="source")
        if self.__last_source is None:
            self.__last_source = self.args["default_source"]
        self.listen_state(self.__state_change, self.__entity_id)
        self.listen_state(
            self.__state_change,
            self.__entity_id,
            attribute="is_volume_muted",
        )
        # TODO: add duration=self.args["steady_state_delay"] when play/pause detectable
        self.listen_state(
            self.__source_change,
            self.__entity_id,
            attribute="source",
            duration=self.args["steady_state_delay"],
        )

    @property
    def is_on(self) -> bool:
        """Check if the TV is currently on or not."""
        return self.get_state(self.__entity_id) == "on"

    @property
    def is_playing(self) -> bool:
        """Check if the TV is currently playing or not."""
        return self.get_state(self.__entity_id) == "on"
        # TODO: update when LG webos supports more than on or off

    @property
    def is_muted(self) -> bool:
        """Check if the TV is currently muted or not."""
        return self.get_state(self.__entity_id, attribute="is_volume_muted")

    @property
    def is_pc_on(self) -> bool:
        """Check if the PC is currently on or not."""
        return subprocess.call(["ping", "-c", "1", self.args["pc_ip"]]) == 0

    def standby(self):
        """Turn the TV off."""
        self.call_service("media_player/turn_off", entity_id=self.__entity_id)
        self.log("TV is now on standby", level="DEBUG")

    def turn_on(self):
        """Turn the TV on."""
        self.call_service("media_player/turn_on", entity_id=self.__entity_id)
        self.log("TV is now on", level="DEBUG")

    def pause(self):
        """Pause media being played on the TV."""
        self.call_service("media_player/media_pause", entity_id=self.__entity_id)
        self.call_service(
            "media_player/volume_mute", is_volume_muted=True, entity_id=self.__entity_id
        )
        self.log("TV media is now paused", level="DEBUG")

    def __state_change(
        self, entity: str, attribute: str, old: str, new: str, kwargs: dict
    ):  # pylint: disable=too-many-arguments
        """Handle TV events at night and change the scene."""
        del entity, attribute, old, kwargs
        if new == "on":
            self.call_service(
                "media_player/select_source",
                source="PC" if self.is_pc_on else self.__last_source,
                entity_id=self.__entity_id,
            )
        if self.control.scene == "Night" and self.is_playing and not self.is_muted:
            self.control.scene = "TV"
        elif self.control.scene == "TV" and (not self.is_playing or self.is_muted):
            self.control.scene = "Night"

    def __source_change(
        self, entity: str, attribute: str, old: str, new: str, kwargs: dict
    ):  # pylint: disable=too-many-arguments
        """Remember TV source before standby so it can be restored when turned on."""
        del entity, attribute, old, kwargs
        if new is not None:
            if new != "PC":
                self.__last_source = new
            self.log(f"TV source changed to {self.__last_source}", level="DEBUG")
