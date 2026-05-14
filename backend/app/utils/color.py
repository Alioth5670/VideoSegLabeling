PALETTE: list[tuple[int, int, int]] = [
    (230, 57, 70),
    (42, 157, 143),
    (69, 123, 157),
    (244, 162, 97),
    (131, 56, 236),
    (46, 196, 182),
    (255, 190, 11),
    (58, 134, 255),
]


def color_for_object(object_id: int) -> tuple[int, int, int]:
    return PALETTE[(object_id - 1) % len(PALETTE)]
