"""Geofence enumerations."""
from __future__ import annotations

from django.db import models


class GeofenceType(models.TextChoices):
    """Supported shapes.

    Both are stored as plain floats so the project needs no PostGIS/GDAL.
    ``RECTANGLE`` replaced an arbitrary ``POLYGON`` type: an axis-aligned
    lat/lon box is the largest shape family that can be evaluated exactly
    without a geometry library.
    """

    CIRCLE = "CIRCLE", "Circle"
    RECTANGLE = "RECTANGLE", "Rectangle (bounding box)"


class ContainmentVerdict(models.TextChoices):
    """Result of comparing one GPS observation against one geofence.

    ``UNCERTAIN`` is a first class outcome, not a failure: it is what the
    system reports while the device is inside the hysteresis band or while its
    accuracy circle straddles a boundary. An ``UNCERTAIN`` reading never
    changes the presence state.
    """

    INSIDE = "INSIDE", "Confidently inside the entry boundary"
    OUTSIDE = "OUTSIDE", "Confidently outside the exit boundary"
    UNCERTAIN = "UNCERTAIN", "Inside the hysteresis band or too imprecise to decide"


class ReadingConfidence(models.TextChoices):
    HIGH = "HIGH", "Accuracy within the acceptable threshold"
    LOW = "LOW", "Accuracy worse than the acceptable threshold"
