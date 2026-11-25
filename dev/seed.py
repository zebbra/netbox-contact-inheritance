# Demo data: a region tree, a large campus and a small branch site, with contacts on several levels.
# Rerunning resets the contact assignments to this state.
from core.models import ObjectType
from dcim.models import Device, DeviceRole, DeviceType, Location, Manufacturer, Rack, Region, Site, SiteGroup
from extras.models import CustomField, CustomFieldChoiceSet
from tenancy.models import Contact, ContactAssignment, ContactGroup, ContactRole
from virtualization.models import Cluster, ClusterType, VirtualMachine


def get(model_cls, **kw):
    defaults = kw.pop('defaults', {})
    return model_cls.objects.get_or_create(**kw, defaults=defaults)[0]


def tree(model, name, parent=None, **extra):
    obj = model.objects.filter(name=name).first()
    if obj is None:
        obj = model(name=name, slug=name.lower().replace(' ', '-').replace('.', ''), parent=parent, **extra)
        obj.save()
    return obj


# Inherit depth custom field on roles (default) and assignments (override)
depth_choices, _ = CustomFieldChoiceSet.objects.update_or_create(
    name='Contact inherit depth',
    defaults={'extra_choices': [
        ['none', 'Only this object'],
        ['site', 'Down to sites'],
        ['location', 'Down to locations (all levels)'],
        ['rack', 'Down to racks'],
        ['device', 'Down to devices and VMs'],
    ]},
)
depth_cf, _ = CustomField.objects.update_or_create(
    name='inherit_depth',
    defaults={
        'type': 'select',
        'label': 'Inherit depth',
        'choice_set': depth_choices,
        'description': 'How far down this contact is inherited. On an assignment it overrides the role default.',
    },
)
depth_cf.object_types.set([
    ObjectType.objects.get_for_model(ContactRole),
    ObjectType.objects.get_for_model(ContactAssignment),
])

# Hierarchy
ch = tree(Region, 'Schweiz')
bern = tree(Region, 'Bern', ch)
zh = tree(Region, 'Zuerich', ch)
campus_group = tree(SiteGroup, 'Campus')
campus = get(Site, name='Bern Campus', defaults={'slug': 'bern-campus', 'region': bern, 'group': campus_group})
branch = get(Site, name='Thun Aussenstelle', defaults={'slug': 'thun', 'region': bern})

bldg_a = tree(Location, 'Gebaeude A', site=campus)
floor1 = tree(Location, '1. OG', bldg_a, site=campus)
room101 = tree(Location, 'Raum 101', floor1, site=campus)
rack101 = get(Rack, name='R101-01', site=campus, defaults={'location': room101})
rack_thun = get(Rack, name='T-01', site=branch)

dc = get(Site, name='RZ Zuerich West', defaults={'slug': 'rz-zuerich-west', 'region': zh})
dc_bldg = tree(Location, 'RZ Gebaeude', site=dc)
dc_floor = tree(Location, 'RZ EG', dc_bldg, site=dc)
dc_room = tree(Location, 'Serverraum 1', dc_floor, site=dc)
dc_rack = get(Rack, name='RZ-A01', site=dc, defaults={'location': dc_room})
office = get(Site, name='Zuerich Oerlikon', defaults={'slug': 'zuerich-oerlikon', 'region': zh, 'group': campus_group})
office_floor = tree(Location, '3. OG', site=office)

mf = get(Manufacturer, name='Generic', defaults={'slug': 'generic'})
dt = get(DeviceType, manufacturer=mf, model='Switch 48', defaults={'slug': 'switch-48'})
srv_t = get(DeviceType, manufacturer=mf, model='Server 1U', defaults={'slug': 'server-1u'})
sw_role = get(DeviceRole, name='Switch', defaults={'slug': 'switch'})
srv_role = get(DeviceRole, name='Server', defaults={'slug': 'server'})

sw_rack = get(Device, name='sw-bern-a-101-01', defaults={
    'device_type': dt, 'role': sw_role, 'site': campus, 'location': room101, 'rack': rack101})
sw_floor = get(Device, name='sw-bern-a-1og', defaults={
    'device_type': dt, 'role': sw_role, 'site': campus, 'location': floor1})
srv_thun = get(Device, name='srv-thun-01', defaults={
    'device_type': srv_t, 'role': srv_role, 'site': branch, 'rack': rack_thun})
sw_thun = get(Device, name='sw-thun-01', defaults={
    'device_type': dt, 'role': sw_role, 'site': branch})
ap_office = get(Device, name='ap-zh-oerlikon-3og-01', defaults={
    'device_type': dt, 'role': sw_role, 'site': office, 'location': office_floor})
srv_dc = get(Device, name='srv-rz-a01-01', defaults={
    'device_type': srv_t, 'role': srv_role, 'site': dc, 'location': dc_room, 'rack': dc_rack})

ctype = get(ClusterType, name='VMware', defaults={'slug': 'vmware'})
cluster = get(Cluster, name='bern-cluster', defaults={'type': ctype, 'scope': campus})
vm = get(VirtualMachine, name='vm-app-01', defaults={'cluster': cluster, 'site': campus})

# Roles with their default inherit depth
facility = get(ContactRole, name='Facility', defaults={'slug': 'facility'})
technical = get(ContactRole, name='Technical', defaults={'slug': 'technical'})
escalation = get(ContactRole, name='Escalation', defaults={'slug': 'escalation'})
for role, depth in ((facility, 'site'), (technical, 'device'), (escalation, None)):
    role.custom_field_data['inherit_depth'] = depth
    role.save()

# Contacts (teams and people)
internal = tree(ContactGroup, 'Intern')
people = {}
for name, email, phone in (
    ('Facility Region Bern', 'facility-bern@example.com', '+41 31 000 00 01'),
    ('Facility Region Zuerich', 'facility-zh@example.com', '+41 44 000 00 01'),
    ('Hauswart Thun', 'hauswart.thun@example.com', '+41 33 000 00 02'),
    ('Hauswart RZ', 'hauswart.rz@example.com', '+41 44 000 00 06'),
    ('Elektriker Gebaeude A', 'elektro-a@example.com', '+41 31 000 00 03'),
    ('NOC', 'noc@example.com', '+41 31 000 00 04'),
    ('Linux Admins', 'linux-admins@example.com', ''),
    ('Pikett IT', 'pikett@example.com', '+41 31 000 00 05'),
    ('Rack Owner Max', 'max@example.com', ''),
):
    p = get(Contact, name=name, defaults={'email': email, 'phone': phone})
    p.groups.add(internal)
    people[name] = p

ContactAssignment.objects.all().delete()


def assign(obj, contact, role, priority='', depth=None):
    a = ContactAssignment(object=obj, contact=people[contact], role=role, priority=priority)
    if depth:
        a.custom_field_data['inherit_depth'] = depth
    a.full_clean()
    a.save()


assign(ch, 'NOC', technical, 'primary')
assign(ch, 'Pikett IT', escalation)
assign(bern, 'Facility Region Bern', facility, 'primary')   # role default: sites only
assign(zh, 'Facility Region Zuerich', facility, 'primary')
assign(campus, 'NOC', technical, 'secondary')              # nearer duplicate of the region NOC
assign(branch, 'Hauswart Thun', facility, 'primary', depth='device')  # small site: he also restarts the server
assign(dc, 'Hauswart RZ', facility, 'primary', depth='location')     # datacenter: building, floors, rooms; racks belong to IT
assign(bldg_a, 'Elektriker Gebaeude A', facility, depth='rack')       # power: down to the racks
assign(bldg_a, 'Linux Admins', technical)
assign(sw_rack, 'Rack Owner Max', technical, 'tertiary')

print('seeded:', ContactAssignment.objects.count(), 'contact assignments')
