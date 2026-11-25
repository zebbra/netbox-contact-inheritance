# End-to-end checks against the seeded demo, run inside the NetBox container:
#   docker compose exec netbox sh -c '/opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py shell < /demo/smoke.py'
# Runs in a transaction that is rolled back at the end.
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import Client

from dcim.models import Device, Location, Rack, Region, Site
from circuits.models import Circuit, CircuitTermination
from netbox_contact_inheritance.circuit_contacts import get_circuit_sections
from netbox_contact_inheritance.reach import get_contact_reach
from netbox_contact_inheritance.resolver import get_effective_contacts
from tenancy.models import Contact
from virtualization.models import VirtualMachine

settings.ALLOWED_HOSTS = [*settings.ALLOWED_HOSTS, 'testserver']  # Django test client host
User = get_user_model()


class Rollback(Exception):
    pass


failed = False


def check(cond, msg):
    global failed
    print(('ok   ' if cond else 'FAIL ') + msg)
    if not cond:
        failed = True


def summary(obj):
    return {
        (ec.assignment.contact.name, ec.assignment.role.name): (str(ec.source) if ec.inherited else 'direct')
        for ec in get_effective_contacts(obj)
    }


def expect(obj, expected):
    got = summary(obj)
    check(got == expected, f'{obj}: {got}' if got != expected else f'{obj}')
    if got != expected:
        print('     expected', expected)


try:
    with transaction.atomic():
        exec(open('/demo/seed.py').read(), {})

        expect(Device.objects.get(name='sw-bern-a-101-01'), {
            ('Rack Owner Max', 'Technical'): 'direct',
            ('Linux Admins', 'Technical'): 'Gebaeude A',
            ('NOC', 'Technical'): 'Bern Campus',
            ('Pikett IT', 'Escalation'): 'Schweiz',
        })
        expect(Location.objects.get(name='Raum 101'), {
            ('Elektriker Gebaeude A', 'Facility'): 'Gebaeude A',
            ('Linux Admins', 'Technical'): 'Gebaeude A',
            ('NOC', 'Technical'): 'Bern Campus',
            ('Pikett IT', 'Escalation'): 'Schweiz',
        })
        expect(Rack.objects.get(name='R101-01'), {
            ('Elektriker Gebaeude A', 'Facility'): 'Gebaeude A',
            ('Linux Admins', 'Technical'): 'Gebaeude A',
            ('NOC', 'Technical'): 'Bern Campus',
            ('Pikett IT', 'Escalation'): 'Schweiz',
        })
        expect(Device.objects.get(name='srv-thun-01'), {
            ('Hauswart Thun', 'Facility'): 'Thun Aussenstelle',
            ('NOC', 'Technical'): 'Schweiz',
            ('Pikett IT', 'Escalation'): 'Schweiz',
        })
        expect(Site.objects.get(name='Bern Campus'), {
            ('Facility Region Bern', 'Facility'): 'Bern',
            ('NOC', 'Technical'): 'direct',
            ('Pikett IT', 'Escalation'): 'Schweiz',
        })
        expect(VirtualMachine.objects.get(name='vm-app-01'), {
            ('NOC', 'Technical'): 'Bern Campus',
            ('Pikett IT', 'Escalation'): 'Schweiz',
        })
        expect(Location.objects.get(name='Serverraum 1'), {
            ('Hauswart RZ', 'Facility'): 'RZ Zuerich West',
            ('NOC', 'Technical'): 'Schweiz',
            ('Pikett IT', 'Escalation'): 'Schweiz',
        })
        expect(Rack.objects.get(name='RZ-A01'), {
            ('NOC', 'Technical'): 'Schweiz',
            ('Pikett IT', 'Escalation'): 'Schweiz',
        })

        # Reverse view: counts per level below each assignment, None = not reached
        def reach(contact):
            return {
                str(r.assignment.object): {k: (c.count if c.reached else None) for k, c in r.cells.items()}
                for r in get_contact_reach(Contact.objects.get(name=contact))
            }

        def expect_reach(contact, expected):
            got = reach(contact)
            check(got == expected, f'reach {contact}' + ('' if got == expected else f': {got}'))
            if got != expected:
                print('     expected', expected)

        expect_reach('NOC', {
            'Schweiz': {'sites': 4, 'locations': 7, 'racks': 3, 'devices': 7, 'vms': 1, 'circuits': None},
            'Bern Campus': {'sites': None, 'locations': 3, 'racks': 1, 'devices': 2, 'vms': 1, 'circuits': None},
        })
        expect_reach('Facility Region Bern', {
            'Bern': {'sites': 2, 'locations': None, 'racks': None, 'devices': None, 'vms': None, 'circuits': None},
        })
        expect_reach('Facility Region Zuerich', {
            'Zuerich': {'sites': 2, 'locations': None, 'racks': None, 'devices': None, 'vms': None, 'circuits': None},
        })
        expect_reach('Hauswart RZ', {
            'RZ Zuerich West': {'sites': None, 'locations': 3, 'racks': None, 'devices': None, 'vms': None, 'circuits': None},
        })
        expect_reach('Hauswart Thun', {
            'Thun Aussenstelle': {'sites': None, 'locations': 0, 'racks': 1, 'devices': 2, 'vms': 0, 'circuits': None},
        })
        expect_reach('Elektriker Gebaeude A', {
            'Gebaeude A': {'sites': None, 'locations': 2, 'racks': 1, 'devices': None, 'vms': None, 'circuits': None},
        })
        expect_reach('Rack Owner Max', {
            'sw-bern-a-101-01': {'sites': None, 'locations': None, 'racks': None, 'devices': None, 'vms': None, 'circuits': None},
        })

        # Circuits: own and provider contacts, then per side the scope and the cabled devices
        def sections(obj):
            out = {}
            for sec in get_circuit_sections(obj):
                out[sec.key] = {
                    (ec.assignment.contact.name, ec.assignment.role.name): (
                        (str(ec.source) if ec.inherited else 'direct') + (f' via {ec.via}' if ec.via else '')
                    )
                    for ec in sec.items
                }
            return out

        def expect_sections(obj, expected):
            got = sections(obj)
            check(got == expected, f'circuit {obj}' + ('' if got == expected else f': {got}'))
            if got != expected:
                print('     expected', expected)

        df = Circuit.objects.get(cid='DF-BE-ZH-001')
        expect_sections(df, {
            'circuit': {
                ('WAN Team', 'Technical'): 'direct',
                ('Fibernet NOC', 'Technical'): 'Fibernet AG',
            },
            'A': {
                ('Elektriker Gebaeude A', 'Facility'): 'Gebaeude A',
                ('Linux Admins', 'Technical'): 'Gebaeude A',
                ('NOC', 'Technical'): 'Bern Campus',
                ('Pikett IT', 'Escalation'): 'Schweiz',
                ('Rack Owner Max', 'Technical'): 'sw-bern-a-101-01 via sw-bern-a-101-01',
            },
            'Z': {
                ('Hauswart RZ', 'Facility'): 'RZ Zuerich West',
                ('NOC', 'Technical'): 'Schweiz',
                ('Pikett IT', 'Escalation'): 'Schweiz',
                ('Server Owner Lea', 'Technical'): 'srv-rz-a01-01 via srv-rz-a01-01',
            },
        })
        expect_sections(Circuit.objects.get(cid='INET-THUN-01'), {
            'circuit': {('Fibernet NOC', 'Technical'): 'Fibernet AG'},
            'A': {
                ('Hauswart Thun', 'Facility'): 'Thun Aussenstelle',
                ('Facility Region Bern', 'Facility'): 'Bern',  # terminates on the site, depth site reaches it
                ('NOC', 'Technical'): 'Schweiz',
                ('Pikett IT', 'Escalation'): 'Schweiz',
            },
        })
        term_z = CircuitTermination.objects.get(circuit=df, term_side='Z')
        z = get_circuit_sections(term_z)
        check(len(z) == 1 and [d.name for d in z[0].devices] == ['srv-rz-a01-01'],
              'termination Z finds the server through the patch panel')
        expect_reach('Fibernet NOC', {
            'Fibernet AG': {'sites': None, 'locations': None, 'racks': None, 'devices': None, 'vms': None,
                            'circuits': 2},
        })
        expect_reach('Fibernet Account Manager', {
            'Fibernet AG': {'sites': None, 'locations': None, 'racks': None, 'devices': None, 'vms': None,
                            'circuits': None},
        })

        admin = User.objects.get(username='admin')
        c = Client()
        c.force_login(admin)
        dev = Device.objects.get(name='sw-bern-a-101-01')

        r = c.get(dev.get_absolute_url())
        html = r.content.decode()
        check(r.status_code == 200 and 'Effective Contacts' in html and 'Linux Admins' in html,
              f'device page shows panel (status {r.status_code})')
        contacts_url = f'/dcim/devices/{dev.pk}/contacts/'
        check(f'href="{contacts_url}">direct</a>' in html, f'"direct" links to {contacts_url}')

        noc = Contact.objects.get(name='NOC')
        ch = Region.objects.get(name='Schweiz')
        r = c.get(noc.get_absolute_url())
        html = r.content.decode()
        check(r.status_code == 200 and 'Reach' in html and f'/dcim/devices/?region_id={ch.pk}' in html,
              f'contact page shows reach with device list link (status {r.status_code})')
        r = c.get(f'/dcim/devices/?region_id={ch.pk}')
        check(r.status_code == 200 and 'srv-rz-a01-01' in r.content.decode(), 'reach link lists the region devices')

        r = c.get('/api/plugins/contact-inheritance/effective-contacts/',
                  {'object_type': 'dcim.device', 'object_id': dev.pk})
        data = r.json() if r.status_code == 200 else {}
        check(r.status_code == 200 and data.get('count') == 4, f'api count 4 (status {r.status_code}, {data.get("count")})')
        noc = next((x for x in data.get('results', []) if x['contact']['name'] == 'NOC'), None)
        check(noc is not None and noc['inherited'] and noc['source']['display'] == 'Bern Campus'
              and noc['contact']['email'] == 'noc@example.com', 'api NOC inherited from Bern Campus with email')

        r = c.get('/api/plugins/contact-inheritance/effective-contacts/',
                  {'object_type': 'dcim.interface', 'object_id': 1})
        check(r.status_code == 400, f'api rejects unsupported type (status {r.status_code})')

        r = c.get(df.get_absolute_url())
        html = r.content.decode()
        check(r.status_code == 200 and 'Side Z' in html and 'Server Owner Lea' in html and 'Fibernet NOC' in html,
              f'circuit page shows sections (status {r.status_code})')
        r = c.get(term_z.get_absolute_url())
        check(r.status_code == 200 and 'Hauswart RZ' in r.content.decode(),
              f'termination page shows its side (status {r.status_code})')
        r = c.get('/api/plugins/contact-inheritance/effective-contacts/',
                  {'object_type': 'circuits.circuit', 'object_id': df.pk})
        data = r.json() if r.status_code == 200 else {}
        lea = next((x for x in data.get('results', []) if x['contact']['name'] == 'Server Owner Lea'), None)
        check(r.status_code == 200 and data.get('count') == 11 and lea and lea['section'] == 'Z'
              and lea['via']['display'] == 'srv-rz-a01-01',
              f'api circuit: 11 entries, Lea on side Z via the server (status {r.status_code}, {data.get("count")})')

        r = c.get('/api/schema/')
        check(r.status_code == 200, f'api schema still renders (status {r.status_code})')

        # A user without contact assignment permission sees no panel
        viewer = User.objects.create_user('viewer', password='x')
        c2 = Client()
        c2.force_login(viewer)
        r = c2.get('/api/plugins/contact-inheritance/effective-contacts/',
                   {'object_type': 'dcim.device', 'object_id': dev.pk})
        check(r.status_code == 404, f'api hides objects the user cannot view (status {r.status_code})')

        raise Rollback
except Rollback:
    pass

print('SMOKE FAILED' if failed else 'SMOKE OK')
