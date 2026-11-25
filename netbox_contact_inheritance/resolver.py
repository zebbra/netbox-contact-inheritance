from collections import defaultdict
from dataclasses import dataclass

from django.conf import settings
from django.db.models import Q

from core.models import ObjectType
from dcim.models import Device, Location, Rack, Region, Site, SiteGroup
from tenancy.models import ContactAssignment
from virtualization.models import VirtualMachine

from .rules import DEFAULT_DEPTH, normalize_depth, pick_nearest, reaches

SUPPORTED_MODELS = (Region, SiteGroup, Site, Location, Rack, Device, VirtualMachine)

LEVEL_LABELS = {
    'region': 'Region',
    'sitegroup': 'Site Group',
    'site': 'Site',
    'location': 'Location',
    'rack': 'Rack',
    'device': 'Device',
}


def plugin_settings():
    cfg = settings.PLUGINS_CONFIG.get('netbox_contact_inheritance', {})
    return {
        'depth_field': cfg.get('depth_field', 'inherit_depth'),
        'default_depth': normalize_depth(cfg.get('default_depth'), DEFAULT_DEPTH),
    }


def _nested(obj, level):
    # MPTT ancestors come root first; we want nearest first
    if obj is None:
        return []
    return [(level, o) for o in reversed(obj.get_ancestors(include_self=True))]


def _site_chain(site):
    if site is None:
        return []
    return [('site', site), *_nested(site.group, 'sitegroup'), *_nested(site.region, 'region')]


def get_chain(obj):
    """
    Return [(level, object), ...] for obj and every ancestor it inherits contacts from, nearest first.
    """
    if isinstance(obj, Device):
        chain = [('device', obj)]
        if obj.rack:
            chain.append(('rack', obj.rack))
        return chain + _nested(obj.location, 'location') + _site_chain(obj.site)
    if isinstance(obj, VirtualMachine):
        # NetBox fills site from the cluster scope on save
        return [('device', obj)] + _site_chain(obj.site)
    if isinstance(obj, Rack):
        return [('rack', obj)] + _nested(obj.location, 'location') + _site_chain(obj.site)
    if isinstance(obj, Location):
        return _nested(obj, 'location') + _site_chain(obj.site)
    if isinstance(obj, Site):
        return _site_chain(obj)
    if isinstance(obj, SiteGroup):
        return _nested(obj, 'sitegroup')
    if isinstance(obj, Region):
        return _nested(obj, 'region')
    raise TypeError(f'Contact inheritance is not supported for {obj._meta.label}')


def resolve_depth(assignment, cfg=None):
    """
    Return (depth, origin) for an assignment. origin is 'assignment', 'role' or 'default'.
    """
    cfg = cfg or plugin_settings()
    field = cfg['depth_field']
    value = assignment.custom_field_data.get(field)
    if value:
        return normalize_depth(value, cfg['default_depth']), 'assignment'
    if assignment.role and (value := assignment.role.custom_field_data.get(field)):
        return normalize_depth(value, cfg['default_depth']), 'role'
    return cfg['default_depth'], 'default'


@dataclass
class EffectiveContact:
    assignment: ContactAssignment
    source: object
    source_level: str
    distance: int
    inherited: bool
    depth: str

    @property
    def source_label(self):
        return LEVEL_LABELS[self.source_level]


def get_effective_contacts(obj, user=None):
    """
    Return the EffectiveContact list for obj: its own assignments plus those inherited from ancestors
    whose inherit depth reaches obj's level. Per contact and role only the nearest assignment is kept.
    """
    cfg = plugin_settings()
    chain = get_chain(obj)
    target_level = chain[0][0]

    position = {}
    ids_by_type = defaultdict(set)
    for distance, (level, node) in enumerate(chain):
        ot = ObjectType.objects.get_for_model(node)
        position[(ot.pk, node.pk)] = (distance, level, node)
        ids_by_type[ot.pk].add(node.pk)

    q = Q()
    for ot_id, ids in ids_by_type.items():
        q |= Q(object_type_id=ot_id, object_id__in=ids)
    qs = ContactAssignment.objects.filter(q).select_related('contact', 'role')
    if user is not None:
        qs = qs.restrict(user, 'view')

    candidates = []
    for a in qs:
        distance, level, node = position[(a.object_type_id, a.object_id)]
        depth, _ = resolve_depth(a, cfg)
        inherited = distance > 0
        if not reaches(target_level, depth, inherited):
            continue
        candidates.append({
            'contact': a.contact_id,
            'role': a.role_id,
            'distance': distance,
            'priority': a.priority,
            'sort_name': a.contact.name,
            'item': EffectiveContact(a, node, level, distance, inherited, depth),
        })

    return [c['item'] for c in pick_nearest(candidates)]
