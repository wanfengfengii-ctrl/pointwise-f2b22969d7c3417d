from collections.abc import Mapping
from dataclasses import dataclass

from .validation import OrderInputError, require_identifier, require_integer


@dataclass(frozen=True, slots=True)
class ChannelScale:
    channel: str
    multiplier: int
    offset: int


@dataclass(frozen=True, slots=True)
class ProfileRevision:
    revision_id: str
    scales: tuple[ChannelScale, ...]

    def for_channel(self, channel: str) -> ChannelScale:
        for scale in self.scales:
            if scale.channel == channel:
                return scale
        raise OrderInputError(f'channel {channel!r} is absent from revision {self.revision_id!r}')


def build_profile(revision_id: str, channels: Mapping[str, tuple[int, int]]) -> ProfileRevision:
    revision_id = require_identifier(revision_id, 'revision ID')
    if not isinstance(channels, Mapping) or not channels:
        raise OrderInputError('a profile needs a nonempty channel mapping')

    scales = []
    for channel, pair in channels.items():
        channel = require_identifier(channel, 'channel')
        if not isinstance(pair, (tuple, list)) or len(pair) != 2:
            raise OrderInputError(f'channel {channel!r} needs a multiplier and offset')
        multiplier = require_integer(pair[0], f'{channel} multiplier')
        offset = require_integer(pair[1], f'{channel} offset')
        scales.append(ChannelScale(channel, multiplier, offset))
    return ProfileRevision(revision_id, tuple(sorted(scales, key=lambda scale: scale.channel)))
