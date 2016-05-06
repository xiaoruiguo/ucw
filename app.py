#!/usr/bin/env python

# requires: pyramid, netaddr, jinja2

import jinja2
import netaddr
from pyramid import config
from pyramid import renderers
from pyramid import response
from pyramid import view
from wsgiref.simple_server import make_server

import validator


config_template = """# Config generated by undercloud wizard
# Use these values in undercloud.conf
[DEFAULT]
undercloud_hostname = %(hostname)s
local_interface = %(local_interface)s
network_cidr = %(network_cidr)s
masquerade_network = %(masquerade_network)s
local_ip = %(local_ip)s
network_gateway = %(network_gateway)s
undercloud_public_vip = %(undercloud_public_vip)s
undercloud_admin_vip = %(undercloud_admin_vip)s
dhcp_start = %(dhcp_start)s
dhcp_end = %(dhcp_end)s
inspection_iprange = %(inspection_start)s,%(inspection_end)s
"""
default_basic = {'local_interface': 'eth1',
                 'network_cidr': '192.0.2.0/24',
                 'node_count': '2'}
advanced_keys = ['hostname', 'local_ip', 'dhcp_start', 'dhcp_end',
                 'introspection_start', 'introspection_end',
                 'network_gateway', 'public_vip', 'admin_vip']
# NOTE(bnemec): Adding an arbitrary 10 to the node count, to allow
# for virtual ips.  This may not be accurate for some setups.
virtual_ips = 10
# local_ip, public_vip, admin_vip
undercloud_ips = 3


class GeneratorError(RuntimeError):
    pass


@view.view_config(route_name='ucw')
def ucw(request):
    # Remove unset keys so we can use .get() to set defaults
    params = {k: v for k, v in request.params.items() if v}
    loader = jinja2.FileSystemLoader('templates')
    env = jinja2.Environment(loader=loader)
    if params.get('generate'):
        t = env.get_template('generate.jinja2')
    else:
        t = env.get_template('ucw.jinja2')
    values = dict(default_basic)
    values['error'] = ''
    for k, v in values.items():
        if k in params:
            values[k] = params[k]
    try:
        cidr = netaddr.IPNetwork(values['network_cidr'])
        if (len(cidr) < int(values['node_count']) * 2 + virtual_ips +
                undercloud_ips + 1):
            raise GeneratorError('Insufficient addresses available in '
                                 'provisioning CIDR')
        values['hostname'] = params.get('hostname', 'undercloud.localdomain')
        values['local_ip'] = '%s/%s' % (str(cidr[1]), cidr.prefixlen)
        values['network_gateway'] = cidr[1]
        values['undercloud_public_vip'] = cidr[2]
        values['undercloud_admin_vip'] = cidr[3]
        # 4 to allow room for two undercloud vips
        dhcp_start = 1 + undercloud_ips
        values['dhcp_start'] = cidr[dhcp_start]
        dhcp_end = dhcp_start + int(values['node_count']) + virtual_ips - 1
        values['dhcp_end'] = cidr[dhcp_end]
        inspection_start = dhcp_end + 1
        values['inspection_start'] = cidr[inspection_start]
        inspection_end = inspection_start + int(values['node_count']) - 1
        values['inspection_end'] = cidr[inspection_end]
        values['masquerade_network'] = values['network_cidr']
        values['config'] = config_template.replace('\n', '<br>') % values
        validator.validate_config(values, lambda x: None)
    except (GeneratorError, validator.FailedValidation) as e:
        values['error'] = str(e)
    return response.Response(t.render(**values))

if __name__ == '__main__':
    conf = config.Configurator()
    conf.add_route('ucw', '/ucw')
    conf.scan()
    app = conf.make_wsgi_app()
    server = make_server('0.0.0.0', 8080, app)
    server.serve_forever()

