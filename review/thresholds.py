class InvalidThreshold(ValueError):
    pass


def validate_threshold(threshold: int) -> int:
    if type(threshold) is not int:
        raise InvalidThreshold('threshold must be an integer in milliunits')
    return threshold


def exceeds_threshold(milliunits: int, threshold: int) -> bool:
    return milliunits > threshold
