import os
from dulwich import porcelain
from packaging import version
from platformdirs import user_data_path

data_path = user_data_path('pyteste')

def update_providers():
    if not os.path.isdir(data_path / 'pyteste'):
        porcelain.clone('https://github.com/RochaSWallace/pyteste', data_path / 'pyteste')
    else:
        porcelain.pull(data_path / 'pyteste')

def get_last_version():
    tags = porcelain.tag_list(data_path / 'pyteste')
    versions_str = [v.decode('utf-8')[1:] for v in tags]
    ordered_versions = sorted(versions_str, key=version.parse)
    return ordered_versions[-1]
