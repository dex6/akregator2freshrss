from __future__ import print_function, division

import os
from datetime import datetime


# Akregator archive directory.
ak_archive_path = os.path.expanduser('~/.local/share/akregator/Archive')

# Name of output zip file.
output_zip = './akregator-export-{}.zip'.format(datetime.today().strftime('%Y-%m-%d-%H-%M'))

# Temporary directory to use for exporting data. Leave None for system default.
temp_dir = None
