from netbox.plugins import PluginTemplateExtension

from .circuit_contacts import get_circuit_sections
from .reach import COLUMN_LABELS, COLUMNS, get_contact_reach
from .resolver import get_effective_contacts



def _can_view(context):
    return context['request'].user.has_perm('tenancy.view_contactassignment')


def _on_contacts_tab(context):
    # The native contacts tab is registered as '<model>_contacts' by ContactsMixin
    match = getattr(context['request'], 'resolver_match', None)
    return bool(match and match.url_name and match.url_name.endswith('_contacts'))


def _contacts_tab_hint(extension, parents):
    """
    One-line hint on the native contacts tab: it shows direct assignments only, prefer parents.
    """
    context = extension.context
    if not _can_view(context) or not _on_contacts_tab(context):
        return ''
    obj = context['object']
    inherited = sum(1 for ec in get_effective_contacts(obj, context['request'].user) if ec.inherited)
    return extension.render('netbox_contact_inheritance/contacts_tab_hint.html', {
        'parents': parents,
        'inherited_count': inherited,
    })


class AllContactsPanel(PluginTemplateExtension):
    """
    On the detail page: all contacts of the object, its own and the inherited ones, each with the
    object it comes from. On the native contacts tab: a hint that it lists direct assignments only.
    """
    models = [
        'dcim.site',
        'dcim.location',
        'dcim.rack',
        'dcim.device',
        'virtualization.virtualmachine',
    ]

    def right_page(self):
        if not _can_view(self.context):
            return ''
        return self.render('netbox_contact_inheritance/effective_contacts.html', {
            'title': 'All Contacts',
            'effective_contacts': get_effective_contacts(self.context['object'], self.context['request'].user),
        })

    def alerts(self):
        return _contacts_tab_hint(self, 'region, site, location, rack')


class CircuitContactsPanel(PluginTemplateExtension):
    """
    All contacts of a circuit (own and provider, then per termination side the scope and the
    cabled devices), or of a single circuit termination. On the circuit's contacts tab: the same hint.
    """
    models = ['circuits.circuit', 'circuits.circuittermination']

    def right_page(self):
        if not _can_view(self.context):
            return ''
        sections = get_circuit_sections(self.context['object'], self.context['request'].user)
        return self.render('netbox_contact_inheritance/circuit_contacts.html', {
            'title': 'All Contacts',
            'sections': sections,
            'show_section_headers': len(sections) > 1 or bool(sections[0].termination),
        })

    def alerts(self):
        return _contacts_tab_hint(self, 'the provider, or the site or location of a termination')


class ContactReachPanel(PluginTemplateExtension):
    """
    Shows on a contact's page, per assignment, how many objects below the assigned object inherit it.
    """
    models = ['tenancy.contact']

    def full_width_page(self):
        if not _can_view(self.context):
            return ''
        return self.render('netbox_contact_inheritance/contact_reach.html', {
            'reach_rows': get_contact_reach(self.context['object'], self.context['request'].user),
            'columns': [(key, COLUMN_LABELS[key]) for key, *_ in COLUMNS],
        })


template_extensions = [AllContactsPanel, CircuitContactsPanel, ContactReachPanel]
