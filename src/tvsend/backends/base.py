"""What every TV back-end offers to the player."""

from typing import NamedTuple, Protocol

# Playback states, shared by all back-ends ('' = the TV did not answer).
PLAYING = "PLAYING"
PAUSED = "PAUSED_PLAYBACK"
LOADING = "TRANSITIONING"
STOPPED = "STOPPED"
NO_MEDIA = "NO_MEDIA_PRESENT"
ACTIVE = (PLAYING, PAUSED, LOADING)
HALTED = (STOPPED, NO_MEDIA)

STATE_TEXT = {
    PLAYING: "playing",
    PAUSED: "PAUSED",
    LOADING: "loading",
    STOPPED: "stopped",
    NO_MEDIA: "stopped",
    "": "TV not answering",
}


class State(NamedTuple):
    state: str  # one of the constants above
    position: float  # seconds
    duration: float  # seconds, 0 when unknown
    uri: str  # what the TV is playing


class Backend(Protocol):
    name: str

    def state(self) -> State: ...

    def load(self, url: str, title: str, mime: str) -> tuple[bool, str]: ...

    def play(self) -> tuple[bool, str]: ...

    def pause(self) -> tuple[bool, str]: ...

    def stop(self) -> tuple[bool, str]: ...

    def seek(self, seconds: float) -> tuple[bool, str]: ...
