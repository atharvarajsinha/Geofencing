"""Initial geofence schema.

Deliberately PostGIS-free: shapes are ordinary float columns and every
geographic comparison happens in Python (see ``common.utils.geo``). A stock
PostgreSQL server is enough - no extension, no GEOS, no GDAL.
"""

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('organizations', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Geofence',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=150)),
                ('geofence_type', models.CharField(choices=[('CIRCLE', 'Circle'), ('RECTANGLE', 'Rectangle (bounding box)')], max_length=16)),
                ('center_latitude', models.FloatField(blank=True, help_text='Circle centre latitude (WGS84). Required for CIRCLE geofences.', null=True)),
                ('center_longitude', models.FloatField(blank=True, help_text='Circle centre longitude (WGS84). Required for CIRCLE geofences.', null=True)),
                ('radius', models.FloatField(blank=True, help_text='Nominal circle radius in metres. Required for CIRCLE geofences.', null=True, validators=[django.core.validators.MinValueValidator(0.0)])),
                ('min_latitude', models.FloatField(help_text='Southern edge (WGS84). The shape itself for a RECTANGLE.')),
                ('max_latitude', models.FloatField(help_text='Northern edge (WGS84). The shape itself for a RECTANGLE.')),
                ('min_longitude', models.FloatField(help_text='Western edge (WGS84). The shape itself for a RECTANGLE.')),
                ('max_longitude', models.FloatField(help_text='Eastern edge (WGS84). The shape itself for a RECTANGLE.')),
                ('entry_radius', models.FloatField(blank=True, help_text='CIRCLE: radius (m) that must be reached to count as inside. RECTANGLE: how far inside the boundary (m) the device must be.', null=True, validators=[django.core.validators.MinValueValidator(0.0)])),
                ('exit_radius', models.FloatField(blank=True, help_text='CIRCLE: radius (m) that must be exceeded to count as outside. RECTANGLE: how far outside the boundary (m) the device must be. Must be greater than entry_radius; the gap is the hysteresis band.', null=True, validators=[django.core.validators.MinValueValidator(0.0)])),
                ('required_inside_readings', models.PositiveSmallIntegerField(blank=True, help_text='Consecutive INSIDE readings needed to check in. Null uses the global default.', null=True)),
                ('required_outside_readings', models.PositiveSmallIntegerField(blank=True, help_text='Consecutive OUTSIDE readings needed to check out. Null uses the global default.', null=True)),
                ('stale_after_seconds', models.PositiveIntegerField(blank=True, help_text='Silence after which a PRESENT user becomes STALE. Null uses the global default.', null=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='geofences', to='organizations.organization')),
            ],
            options={
                'db_table': 'geofences_geofence',
                'ordering': ('name',),
                'indexes': [
                    models.Index(fields=['organization', 'is_active'], name='geofence_org_active_idx'),
                    models.Index(fields=['geofence_type'], name='geofence_type_idx'),
                    models.Index(fields=['min_latitude', 'max_latitude'], name='geofence_bbox_lat_idx'),
                    models.Index(fields=['min_longitude', 'max_longitude'], name='geofence_bbox_lon_idx'),
                ],
                'constraints': [
                    models.UniqueConstraint(fields=('organization', 'name'), name='geofence_unique_name_per_org'),
                    models.CheckConstraint(condition=models.Q(models.Q(('center_latitude__isnull', False), ('center_longitude__isnull', False), ('geofence_type', 'CIRCLE'), ('radius__isnull', False)), ('geofence_type', 'RECTANGLE'), _connector='OR'), name='geofence_shape_matches_type'),
                    models.CheckConstraint(condition=models.Q(('radius__isnull', True), ('radius__gt', 0), _connector='OR'), name='geofence_radius_positive'),
                    models.CheckConstraint(condition=models.Q(('entry_radius__isnull', True), ('exit_radius__isnull', True), ('exit_radius__gt', models.F('entry_radius')), _connector='OR'), name='geofence_exit_radius_greater_than_entry'),
                    models.CheckConstraint(condition=models.Q(('max_latitude__gt', models.F('min_latitude'))), name='geofence_bbox_latitude_ordered'),
                    models.CheckConstraint(condition=models.Q(('max_longitude__gt', models.F('min_longitude'))), name='geofence_bbox_longitude_ordered'),
                ],
            },
        ),
    ]
