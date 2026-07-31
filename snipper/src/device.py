def resolve_dimensions(screen_width: int, screen_height: int, orientation: str):
    """
    Portrait device watching landscape video → swap dimensions so
    the encode matches what the screen looks like when rotated.
    Returns (target_width, target_height, needs_rotate_prompt)
    """
    is_portrait = "portrait" in (orientation or "").lower()
    if is_portrait:
        return screen_height, screen_width, True
    return screen_width, screen_height, False
