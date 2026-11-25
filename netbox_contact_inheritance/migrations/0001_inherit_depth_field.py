"""
Create the inherit depth custom field on contact roles and contact assignments.

Runs once with `manage.py migrate`. An existing field of the same name is kept as is; only the two
object types are added to it. Rolling back leaves the field in place, since it may hold data.
"""
from django.conf import settings
from django.db import migrations

CHOICES = [
    ['none', 'Only this object'],
    ['site', 'Down to sites'],
    ['location', 'Down to locations (all levels)'],
    ['rack', 'Down to racks'],
    ['device', 'Down to devices and VMs'],
]


def create_field(apps, schema_editor):
    CustomField = apps.get_model('extras', 'CustomField')
    CustomFieldChoiceSet = apps.get_model('extras', 'CustomFieldChoiceSet')
    ContentType = apps.get_model('contenttypes', 'ContentType')

    cfg = settings.PLUGINS_CONFIG.get('netbox_contact_inheritance', {})
    name = cfg.get('depth_field', 'inherit_depth')

    field = CustomField.objects.filter(name=name).first()
    if field is None:
        choice_set, _ = CustomFieldChoiceSet.objects.get_or_create(
            name='Contact inherit depth',
            defaults={'extra_choices': CHOICES},
        )
        field = CustomField.objects.create(
            name=name,
            type='select',
            label='Inherit depth',
            choice_set=choice_set,
            description='How far down this contact is inherited. On an assignment it overrides the role default.',
        )
    for model in ('contactrole', 'contactassignment'):
        ct, _ = ContentType.objects.get_or_create(app_label='tenancy', model=model)
        field.object_types.add(ct)


class Migration(migrations.Migration):

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        ('extras', '0140_imageattachment_image_size'),
        ('tenancy', '0024_default_ordering_indexes'),
    ]

    operations = [
        migrations.RunPython(create_field, migrations.RunPython.noop),
    ]
