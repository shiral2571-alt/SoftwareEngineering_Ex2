# Homework 3 - shapes with polymorphism
from abc import ABC, abstractmethod
import math


class Shape(ABC):
    @abstractmethod
    def area(self) -> float: ...


class Circle(Shape):
    def __init__(self, r):
        self.r = r

    def area(self):
        return math.pi * self.r ** 2


class Rectangle(Shape):
    def __init__(self, w, h):
        self.w, self.h = w, h

    def area(self):
        return self.w * self.h


def total_area(shapes):
    # works for any new Shape without changing this function (Open/Closed)
    return sum(s.area() for s in shapes)
