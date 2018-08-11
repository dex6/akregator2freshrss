from __future__ import print_function, division

import os
from datetime import datetime


# Akregator archive directory.
ak_archive_path = os.path.expanduser('~/.local/share/akregator/Archive')

# Name of output zip file.
output_zip = './akregator-export-{}.zip'.format(datetime.today().strftime('%Y-%m-%d-%H-%M'))

# Temporary directory to use for exporting data. Leave None for system default.
temp_dir = None

# FreshRSS user name (which you use to login into your FreshRSS instance via www)
freshrss_username = 'user'

# FreshRSS DB connection data (currently only MySQL is supported)
frdb_host = '127.0.0.1'   # empty string to connect via local UNIX socket
frdb_user = 'freshrss'
frdb_pass = 'password'
frdb_name = 'freshrss'
frdb_table_prefix = 'freshrss_{}_'.format(freshrss_username)
