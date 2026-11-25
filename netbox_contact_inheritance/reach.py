"""
The reverse view of inheritance: which objects below an assignment's object inherit it.

Objects are counted per level, not listed. Each count links to the regular NetBox list with the
filter that selects the same objects, so paging and export come from NetBox.
"""
from dataclasses import dataclass
from urllib.parse import urlencode

from django.urls import reverse

from dcim.models import Device, Location, Rack, Region, Site, SiteGroup
from virtualization.models import VirtualMachine

from .resolver import resolve_depth
from .rules import reaches

# (column key, level used for the depth check, model, list view)
COLUMNS = (
    ('sites', 'site', Site, 'dcim:site_list'),
    ('locations', 'location', Location, 'dcim:location_list'),
    ('racks', 'rack', Rack, 'dcim:rack_list'),
    ('devices', 'device', Device, 'dcim:device_list'),
    ('vms', 'device', VirtualMachine, 'virtualization:virtualmachine_list'),
)
COLUMN_LABELS = {'sites': 'Sites', 'locations': 'Locations', 'racks': 'Racks', 'devices': 'Devices', 'vms': 'VMs'}


def _scopes(obj):
    """
    Per column: (queryset filter, list URL parameters) for the objects below obj, or None if the
    column cannot be below obj.
    """
    if isinstance(obj, Region):
        tree = obj.get_descendants(include_self=True)
        below = {'site__region__in': tree}
        params = {'region_id': obj.pk}
        return {
            'sites': ({'region__in': tree}, params),
            'locations': (below, params),
            'racks': (below, params),
            'devices': (below, params),
            'vms': (below, params),
        }
    if isinstance(obj, SiteGroup):
        tree = obj.get_descendants(include_self=True)
        below = {'site__group__in': tree}
        params = {'site_group_id': obj.pk}
        return {
            'sites': ({'group__in': tree}, {'group_id': obj.pk}),
            'locations': (below, params),
            'racks': (below, params),
            'devices': (below, params),
            'vms': (below, params),
        }
    if isinstance(obj, Site):
        params = {'site_id': obj.pk}
        return {
            'locations': ({'site': obj}, params),
            'racks': ({'site': obj}, params),
            'devices': ({'site': obj}, params),
            'vms': ({'site': obj}, params),
        }
    if isinstance(obj, Location):
        tree = obj.get_descendants(include_self=True)
        params = {'location_id': obj.pk}
        return {
            'locations': ({'pk__in': obj.get_descendants()}, {'ancestor_id': obj.pk}),
            'racks': ({'location__in': tree}, params),
            'devices': ({'location__in': tree}, params),
        }
    if isinstance(obj, Rack):
        return {'devices': ({'rack': obj}, {'rack_id': obj.pk})}
    return {}


@dataclass
class ReachCell:
    reached: bool
    count: int = 0
    url: str = ''


@dataclass
class ReachRow:
    assignment: object
    depth: str
    depth_origin: str
    cells: dict


def get_reach(assignment, user=None):
    depth, origin = resolve_depth(assignment)
    scopes = _scopes(assignment.object) if assignment.object is not None else {}
    cells = {}
    for key, level, model, viewname in COLUMNS:
        scope = scopes.get(key)
        if scope is None or not reaches(level, depth):
            cells[key] = ReachCell(reached=False)
            continue
        filters, params = scope
        qs = model.objects.filter(**filters)
        if user is not None:
            qs = qs.restrict(user, 'view')
        cells[key] = ReachCell(reached=True, count=qs.count(), url=f'{reverse(viewname)}?{urlencode(params)}')
    return ReachRow(assignment, depth, origin, cells)


def get_contact_reach(contact, user=None):
    assignments = contact.assignments.select_related('role', 'object_type')
    if user is not None:
        assignments = assignments.restrict(user, 'view')
    return [get_reach(a, user) for a in assignments.order_by('object_type', 'object_id', 'role')]
