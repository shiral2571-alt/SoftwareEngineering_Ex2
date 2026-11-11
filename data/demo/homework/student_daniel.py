import math


def area(shape):
    if shape["type"] == "circle":
        return math.pi * shape["r"] ** 2
    elif shape["type"] == "rectangle":
        return shape["w"] * shape["h"]
    elif shape["type"] == "square":
        return shape["side"] ** 2
    return 0


def total_area(shapes):
    t = 0
    for s in shapes:
        t = t + area(s)
    return t
