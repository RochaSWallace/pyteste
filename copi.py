import shutil
from platformdirs import user_config_dir
from pathlib import Path

# Caminhos antigos e novos
old_config_path = Path(user_config_dir('pyneko'))
new_config_path = Path(user_config_dir('pyteste'))

# Arquivo do banco de dados
old_db = old_config_path / 'ui.db'
new_db = new_config_path / 'ui.db'

# Cria o novo diretório se não existir
new_config_path.mkdir(parents=True, exist_ok=True)

# Copia o arquivo se ele existir
if old_db.exists():
    shutil.copy2(old_db, new_db)
    print(f'Arquivo copiado de {old_db} para {new_db}')
else:
    print('Arquivo antigo não encontrado.')