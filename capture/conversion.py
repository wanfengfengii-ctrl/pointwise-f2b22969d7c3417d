from orders.profiles import ChannelScale


class InvalidRawCount(ValueError):
    pass


def convert_count(raw_count: int, scale: ChannelScale) -> int:
    if type(raw_count) is not int:
        raise InvalidRawCount('raw count must be an integer')
    return raw_count * scale.multiplier + scale.offset
