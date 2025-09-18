#!/usr/bin/env python3
"""
Script simples para testar o GitHub Secret PYTESTE_APP_SECRET
"""
import os
import sys
import hashlib
import time
from pathlib import Path

def test_github_secret():
    """Testa se o GitHub Secret está disponível e funcional"""
    
    print("TESTANDO GITHUB SECRET...")
    print("=" * 50)
    
    # 1. Verifica se secret está disponível
    github_secret = os.environ.get('PYTESTE_APP_SECRET')
    
    if not github_secret:
        print("ERRO: PYTESTE_APP_SECRET nao encontrado no ambiente!")
        print("Variaveis disponiveis:")
        for key in os.environ:
            if 'SECRET' in key.upper() or 'PYTESTE' in key.upper():
                print(f"  - {key}")
        return False
    
    print("OK: PYTESTE_APP_SECRET encontrado!")
    print(f"Tamanho: {len(github_secret)} caracteres")
    print(f"Primeiros 8 chars: {github_secret[:8]}...")
    print(f"Ultimos 8 chars: ...{github_secret[-8:]}")
    
    # 2. Testa geração de hash
    try:
        secret_hash = hashlib.sha256(github_secret.encode()).hexdigest()
        print(f"Hash SHA256: {secret_hash[:16]}...")
        
        # 3. Testa combinação com timestamp
        timestamp = str(int(time.time()))
        combined = f"{github_secret}-{timestamp}"
        combined_hash = hashlib.sha256(combined.encode()).hexdigest()
        print(f"Com timestamp: {combined_hash[:16]}...")
        
        # 4. Cria arquivo de teste
        test_content = f"""# Teste do GitHub Secret - {time.strftime('%Y-%m-%d %H:%M:%S')}

# Secret hash (primeiros 16 chars)
SECRET_HASH_PREVIEW = "{secret_hash[:16]}"

# Timestamp do teste
TEST_TIMESTAMP = "{timestamp}"

# Função de teste
def verify_secret_test():
    return len(SECRET_HASH_PREVIEW) == 16

def get_test_info():
    return {{
        "secret_available": True,
        "secret_length": {len(github_secret)},
        "hash_preview": SECRET_HASH_PREVIEW,
        "timestamp": TEST_TIMESTAMP
    }}
"""
        
        # Escreve arquivo de teste
        test_file = Path('test_secret_output.py')
        test_file.write_text(test_content, encoding='utf-8')
        print(f"Arquivo de teste criado: {test_file}")
        
        print("\nTeste do GitHub Secret: SUCESSO!")
        return True
        
    except (ValueError, TypeError, OSError) as e:
        print(f"ERRO durante teste: {e}")
        return False

def test_local_fallback():
    """Testa fallback para desenvolvimento local"""
    print("\nTestando fallback local...")
    
    # Simula secret local
    local_secret = "dev-local-secret-for-testing-2025"
    local_hash = hashlib.sha256(local_secret.encode()).hexdigest()
    
    print(f"Secret local: {local_secret[:16]}...")
    print(f"Hash local: {local_hash[:16]}...")
    
    return True

if __name__ == "__main__":
    print("Iniciando teste do sistema de secrets...")
    print()
    
    # Teste principal
    github_success = test_github_secret()
    
    # Teste de fallback
    local_success = test_local_fallback()
    
    print("\n" + "=" * 50)
    print("RESUMO DOS TESTES:")
    print(f"  GitHub Secret: {'OK' if github_success else 'FALHOU'}")
    print(f"  Local Fallback: {'OK' if local_success else 'FALHOU'}")
    
    if github_success:
        print("\nPRONTO PARA IMPLEMENTACAO!")
        sys.exit(0)
    else:
        print("\nVERIFICAR CONFIGURACAO DO SECRET")
        sys.exit(1)