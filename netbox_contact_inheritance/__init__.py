from netbox.plugins import PluginConfig

__version__ = '0.1.0'


class ContactInheritanceConfig(PluginConfig):
    name = 'netbox_contact_inheritance'
    verbose_name = 'Contact Inheritance'
    description = 'Show contacts inherited from region, site, location and rack on the objects below them'
    version = __version__
    author = 'Stefan Grosser'
    base_url = 'contact-inheritance'
    min_version = '4.6.5'
    default_settings = {
        'depth_field': 'inherit_depth',
        'default_depth': 'device',
    }


config = ContactInheritanceConfig
