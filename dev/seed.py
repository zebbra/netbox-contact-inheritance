# Demo data: a region tree, a large campus and a small branch site, with contacts on several levels.
# Rerunning resets the contact assignments to this state.
from circuits.models import Circuit, CircuitTermination, CircuitType, Provider
from dcim.models import (
    Cable, Device, DeviceRole, DeviceType, FrontPort, Interface, Location, Manufacturer, PortMapping, Rack, RearPort,
    Region, Site, SiteGroup,
)
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


# The inherit_depth custom field is created by the plugin migration

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

# Circuits: a dark fiber Bern - Zurich (side Z through a patch panel) and an uncabled internet line in Thun
pp_t = get(DeviceType, manufacturer=mf, model='Patch Panel 24', defaults={'slug': 'patch-panel-24'})
pp_role = get(DeviceRole, name='Patch Panel', defaults={'slug': 'patch-panel'})
pp = get(Device, name='pp-rz-a01', defaults={
    'device_type': pp_t, 'role': pp_role, 'site': dc, 'location': dc_room, 'rack': dc_rack})
if_bern = get(Interface, device=sw_rack, name='Gi1/0/48', defaults={'type': '1000base-x-sfp'})
if_dc = get(Interface, device=srv_dc, name='eth0', defaults={'type': '10gbase-x-sfpp'})
rp = get(RearPort, device=pp, name='RP1', defaults={'type': 'lc'})
fp = get(FrontPort, device=pp, name='FP1', defaults={'type': 'lc'})
if not PortMapping.objects.filter(front_port=fp).exists():
    PortMapping.objects.create(device=pp, front_port=fp, front_port_position=1, rear_port=rp, rear_port_position=1)

provider = get(Provider, name='Fibernet AG', defaults={'slug': 'fibernet'})
df_type = get(CircuitType, name='Dark Fiber', defaults={'slug': 'dark-fiber'})
inet_type = get(CircuitType, name='Internet', defaults={'slug': 'internet'})
df = get(Circuit, cid='DF-BE-ZH-001', provider=provider, defaults={'type': df_type})
inet = get(Circuit, cid='INET-THUN-01', provider=provider, defaults={'type': inet_type})


def termination(circuit, side, scope):
    t = CircuitTermination.objects.filter(circuit=circuit, term_side=side).first()
    if t is None:
        t = CircuitTermination(circuit=circuit, term_side=side, termination=scope)
        t.save()
    return t


term_a = termination(df, 'A', room101)
term_z = termination(df, 'Z', dc_room)
termination(inet, 'A', branch)


def cable(a, b):
    if not a.cable and not b.cable:
        Cable(a_terminations=[a], b_terminations=[b]).save()


cable(term_a, if_bern)
cable(term_z, rp)
cable(fp, if_dc)

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
    ('Server Owner Lea', 'lea@example.com', ''),
    ('WAN Team', 'wan@example.com', '+41 31 000 00 07'),
    ('Fibernet NOC', 'noc@fibernet.example', '+41 800 000 001'),
    ('Fibernet Account Manager', 'sales@fibernet.example', ''),
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
assign(srv_dc, 'Server Owner Lea', technical)
assign(df, 'WAN Team', technical, 'primary')
assign(provider, 'Fibernet NOC', technical, 'secondary')
assign(provider, 'Fibernet Account Manager', escalation, depth='none')  # stays on the provider

print('seeded:', ContactAssignment.objects.count(), 'contact assignments')
