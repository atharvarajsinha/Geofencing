"""Geofence model.

No PostGIS. Both supported shapes are stored as plain floats and reduced to the
same decision problem: a *signed distance* ``x`` (metres) and two thresholds.

========= ==================================== ========================= =========================
type      x                                    enter when                exit when
========= ==================================== ========================= =========================
CIRCLE    distance to the centre               ``x <= entry_radius``     ``x >= exit_radius``
RECTANGLE signed distance to the box boundary  ``x <= -entry_radius``    ``x >= +exit_radius``
          (negative inside)                    (inset)                   (outset)
========= ==================================== ========================= =========================

Keeping one axis for both types means the presence state machine never needs to
know which shape it is dealing with.

Every geofence - circle included - also stores its bounding box in
``min_latitude``/``max_latitude``/``min_longitude``/``max_longitude``. For a
RECTANGLE that box *is* the shape; for a CIRCLE it is a derived envelope,
maintained by :meth:`Geofence.refresh_bounding_box`, that lets the evaluator
prefilter candidates with an ordinary B-tree index.
"""
from __future__ import annotations

from math import cos, radians

from django.core.validators import MinValueValidator
from django.db import models

from common.conf import geo_conf
from common.utils.geo import (
    METRES_PER_DEGREE_LATITUDE,
    bbox_for_circle,
    haversine_distance_m,
    signed_distance_to_bbox_m,
)
from geofences.enums import GeofenceType


class GeofenceQuerySet(models.QuerySet):
    def active(self) -> "GeofenceQuerySet":
        return self.filter(is_active=True)

    def for_organization(self, organization_id: int) -> "GeofenceQuerySet":
        return self.filter(organization_id=organization_id)

    def bbox_contains_within(self, latitude: float, longitude: float, margin_m: float):
        """Candidates whose bounding box, grown by ``margin_m``, holds the point.

        A pure index-friendly prefilter: it must never exclude a geofence the
        exact test would have accepted, so the margin has to cover the exit
        threshold plus the accuracy margin. Callers that cannot bound the margin
        should not use this.
        """
        lat_pad = margin_m / METRES_PER_DEGREE_LATITUDE
        # One degree of longitude shrinks with latitude, so the same distance
        # spans more degrees further from the equator. Clamp the cosine so a
        # near-polar fix widens the window instead of dividing by ~zero.
        cos_lat = cos(radians(min(abs(latitude), 85.0)))
        lon_pad = 180.0 if cos_lat <= 1e-6 else lat_pad / cos_lat
        return self.filter(
            min_latitude__lte=latitude + lat_pad,
            max_latitude__gte=latitude - lat_pad,
            min_longitude__lte=longitude + lon_pad,
            max_longitude__gte=longitude - lon_pad,
        )


class Geofence(models.Model):
    """An area an organization tracks presence in."""

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="geofences",
    )
    name = models.CharField(max_length=150)
    geofence_type = models.CharField(max_length=16, choices=GeofenceType.choices)

    # --- CIRCLE ---------------------------------------------------------
    center_latitude = models.FloatField(
        null=True,
        blank=True,
        help_text="Circle centre latitude (WGS84). Required for CIRCLE geofences.",
    )
    center_longitude = models.FloatField(
        null=True,
        blank=True,
        help_text="Circle centre longitude (WGS84). Required for CIRCLE geofences.",
    )
    radius = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0.0)],
        help_text="Nominal circle radius in metres. Required for CIRCLE geofences.",
    )

    # --- RECTANGLE, and the derived envelope of a CIRCLE ------------------
    #
    # Always populated. For a RECTANGLE these four numbers are the geofence; for
    # a CIRCLE they are the circle's bounding box, kept in sync on save.
    min_latitude = models.FloatField(
        help_text="Southern edge (WGS84). The shape itself for a RECTANGLE."
    )
    max_latitude = models.FloatField(
        help_text="Northern edge (WGS84). The shape itself for a RECTANGLE."
    )
    min_longitude = models.FloatField(
        help_text="Western edge (WGS84). The shape itself for a RECTANGLE."
    )
    max_longitude = models.FloatField(
        help_text="Eastern edge (WGS84). The shape itself for a RECTANGLE."
    )

    # --- Hysteresis ------------------------------------------------------
    entry_radius = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0.0)],
        help_text=(
            "CIRCLE: radius (m) that must be reached to count as inside. "
            "RECTANGLE: how far inside the boundary (m) the device must be."
        ),
    )
    exit_radius = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0.0)],
        help_text=(
            "CIRCLE: radius (m) that must be exceeded to count as outside. "
            "RECTANGLE: how far outside the boundary (m) the device must be. "
            "Must be greater than entry_radius; the gap is the hysteresis band."
        ),
    )

    # --- Per-geofence overrides of the global tunables --------------------
    required_inside_readings = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Consecutive INSIDE readings needed to check in. Null uses the global default.",
    )
    required_outside_readings = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Consecutive OUTSIDE readings needed to check out. Null uses the global default.",
    )
    stale_after_seconds = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Silence after which a PRESENT user becomes STALE. Null uses the global default.",
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = GeofenceQuerySet.as_manager()

    class Meta:
        db_table = "geofences_geofence"
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"], name="geofence_unique_name_per_org"
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        geofence_type=GeofenceType.CIRCLE,
                        center_latitude__isnull=False,
                        center_longitude__isnull=False,
                        radius__isnull=False,
                    )
                    | models.Q(geofence_type=GeofenceType.RECTANGLE)
                ),
                name="geofence_shape_matches_type",
            ),
            models.CheckConstraint(
                condition=models.Q(radius__isnull=True) | models.Q(radius__gt=0),
                name="geofence_radius_positive",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(entry_radius__isnull=True)
                    | models.Q(exit_radius__isnull=True)
                    | models.Q(exit_radius__gt=models.F("entry_radius"))
                ),
                name="geofence_exit_radius_greater_than_entry",
            ),
            # A degenerate box would make every verdict UNCERTAIN.
            models.CheckConstraint(
                condition=models.Q(max_latitude__gt=models.F("min_latitude")),
                name="geofence_bbox_latitude_ordered",
            ),
            models.CheckConstraint(
                condition=models.Q(max_longitude__gt=models.F("min_longitude")),
                name="geofence_bbox_longitude_ordered",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "is_active"], name="geofence_org_active_idx"),
            models.Index(fields=["geofence_type"], name="geofence_type_idx"),
            # Supports the bounding-box prefilter in the evaluator.
            models.Index(
                fields=["min_latitude", "max_latitude"], name="geofence_bbox_lat_idx"
            ),
            models.Index(
                fields=["min_longitude", "max_longitude"], name="geofence_bbox_lon_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} [{self.geofence_type}]"

    # -- Shape bookkeeping -----------------------------------------------
    @property
    def is_circle(self) -> bool:
        return self.geofence_type == GeofenceType.CIRCLE

    @property
    def is_rectangle(self) -> bool:
        return self.geofence_type == GeofenceType.RECTANGLE

    def refresh_bounding_box(self) -> None:
        """Recompute the envelope of a CIRCLE from its centre and radius.

        A no-op for a RECTANGLE, whose box is authored directly.
        """
        if not self.is_circle:
            return
        if self.center_latitude is None or self.center_longitude is None:
            return
        (
            self.min_latitude,
            self.max_latitude,
            self.min_longitude,
            self.max_longitude,
        ) = bbox_for_circle(
            float(self.center_latitude),
            float(self.center_longitude),
            float(self.radius or 0.0),
        )

    def save(self, *args, **kwargs):
        """Keep a circle's envelope consistent with its centre and radius."""
        self.refresh_bounding_box()
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and self.is_circle:
            touches_shape = {"center_latitude", "center_longitude", "radius"} & set(
                update_fields
            )
            if touches_shape:
                kwargs["update_fields"] = {
                    *update_fields,
                    "min_latitude",
                    "max_latitude",
                    "min_longitude",
                    "max_longitude",
                }
        return super().save(*args, **kwargs)

    # -- Geometry ---------------------------------------------------------
    def signed_distance_m(self, latitude: float, longitude: float) -> float:
        """Signed distance in metres from a fix to this geofence's boundary.

        Negative inside, positive outside. This is the single geometric
        primitive the evaluator needs, and it runs entirely in Python.
        """
        if self.is_circle:
            distance = haversine_distance_m(
                latitude,
                longitude,
                float(self.center_latitude),
                float(self.center_longitude),
            )
            return distance - float(self.radius or 0.0)

        return signed_distance_to_bbox_m(
            latitude,
            longitude,
            min_latitude=float(self.min_latitude),
            max_latitude=float(self.max_latitude),
            min_longitude=float(self.min_longitude),
            max_longitude=float(self.max_longitude),
        )

    def axis_value_m(self, latitude: float, longitude: float) -> float:
        """Position of a fix on this geofence's comparison axis.

        For a circle that is the raw distance to the centre (so the thresholds
        are radii); for a rectangle it is the signed boundary distance.
        """
        if self.is_circle:
            return haversine_distance_m(
                latitude,
                longitude,
                float(self.center_latitude),
                float(self.center_longitude),
            )
        return self.signed_distance_m(latitude, longitude)

    # -- Derived configuration -------------------------------------------
    @property
    def effective_entry_threshold_m(self) -> float:
        """Threshold on the signed-distance axis below which a fix is INSIDE."""
        if self.is_circle:
            if self.entry_radius is not None:
                return float(self.entry_radius)
            return max(
                float(self.radius or 0.0) - geo_conf.DEFAULT_ENTRY_BUFFER_M,
                geo_conf.MIN_RADIUS_M,
            )
        # Rectangle: an inset expressed as a negative signed distance.
        inset = (
            float(self.entry_radius)
            if self.entry_radius is not None
            else geo_conf.DEFAULT_ENTRY_BUFFER_M
        )
        return -inset

    @property
    def effective_exit_threshold_m(self) -> float:
        """Threshold on the signed-distance axis above which a fix is OUTSIDE."""
        if self.is_circle:
            if self.exit_radius is not None:
                return float(self.exit_radius)
            return float(self.radius or 0.0) + geo_conf.DEFAULT_EXIT_BUFFER_M
        outset = (
            float(self.exit_radius)
            if self.exit_radius is not None
            else geo_conf.DEFAULT_EXIT_BUFFER_M
        )
        return outset

    @property
    def effective_required_inside_readings(self) -> int:
        return int(
            self.required_inside_readings
            if self.required_inside_readings is not None
            else geo_conf.REQUIRED_INSIDE_READINGS
        )

    @property
    def effective_required_outside_readings(self) -> int:
        return int(
            self.required_outside_readings
            if self.required_outside_readings is not None
            else geo_conf.REQUIRED_OUTSIDE_READINGS
        )

    @property
    def effective_stale_after_seconds(self) -> int:
        return int(
            self.stale_after_seconds
            if self.stale_after_seconds is not None
            else geo_conf.STALE_AFTER_SECONDS
        )

    # -- Presentation helpers --------------------------------------------
    @property
    def latitude(self) -> float | None:
        """Representative latitude: the circle centre, or the box centre."""
        if self.is_circle:
            return self.center_latitude
        if self.min_latitude is None or self.max_latitude is None:
            return None
        return (float(self.min_latitude) + float(self.max_latitude)) / 2.0

    @property
    def longitude(self) -> float | None:
        if self.is_circle:
            return self.center_longitude
        if self.min_longitude is None or self.max_longitude is None:
            return None
        return (float(self.min_longitude) + float(self.max_longitude)) / 2.0

    @property
    def bounds(self) -> dict[str, float]:
        """The four numbers a client needs to draw this geofence."""
        return {
            "min_latitude": float(self.min_latitude),
            "max_latitude": float(self.max_latitude),
            "min_longitude": float(self.min_longitude),
            "max_longitude": float(self.max_longitude),
        }
