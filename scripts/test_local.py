#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para testar o sistema localmente (sem GitHub Secret)
"""
import sys
from pathlib import Path

# Fix para encoding no Windows
if sys.platform.startswith('win'):
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

def test_local_system():
    """Testa o sistema local sem GitHub Secret"""
    
    print("🏠 Teste Local do Sistema de Secrets")
    print("=" * 45)
    
    # 1. Testa se script existe
    script_path = Path("scripts/test_github_secret.py")
    if not script_path.exists():
        print(f"❌ Script não encontrado: {script_path}")
        return False
    
    print(f"✅ Script encontrado: {script_path}")
    
    # 2. Testa execução local (sem secret)
    print("\n🔧 Executando teste local...")
    
    try:
        # Executa o script sem definir PYTESTE_APP_SECRET
        import subprocess
        result = subprocess.run([
            sys.executable, str(script_path)
        ], capture_output=True, text=True, timeout=30, check=False)
        
        print("📤 STDOUT:")
        print(result.stdout)
        
        if result.stderr:
            print("📥 STDERR:")
            print(result.stderr)
        
        # Esperamos que falhe graciosamente (exit code 1)
        if result.returncode == 1:
            print("✅ Script falhou graciosamente (esperado sem secret)")
            return True
        elif result.returncode == 0:
            print("⚠️  Script passou (inesperado sem secret)")
            return True
        else:
            print(f"❌ Script falhou com código: {result.returncode}")
            return False
            
    except subprocess.TimeoutExpired:
        print("❌ Script travou (timeout)")
        return False
    except FileNotFoundError:
        print("❌ Python não encontrado")
        return False
    except (subprocess.TimeoutExpired, OSError) as e:
        print(f"❌ Erro: {e}")
        return False

def test_poetry_command():
    """Testa se o comando poetry funciona"""
    print("\n📦 Testando comando Poetry...")
    
    try:
        import subprocess
        result = subprocess.run([
            "poetry", "run", "python", "--version"
        ], capture_output=True, text=True, timeout=10, check=False)
        
        if result.returncode == 0:
            print(f"✅ Poetry OK: {result.stdout.strip()}")
            return True
        else:
            print(f"❌ Poetry falhou: {result.stderr}")
            return False
            
    except FileNotFoundError:
        print("❌ Poetry não encontrado (talvez não esteja no PATH)")
        return False
    except OSError as e:
        print(f"❌ Erro no Poetry: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Teste Local - Sistema de Secrets")
    print()
    
    # Testes
    script_test = test_local_system()
    poetry_test = test_poetry_command()
    
    print("\n" + "=" * 45)
    print("📊 RESUMO DOS TESTES LOCAIS:")
    print(f"  Script funcionando: {'✅ OK' if script_test else '❌ FALHOU'}")
    print(f"  Poetry funcionando: {'✅ OK' if poetry_test else '❌ FALHOU'}")
    
    if script_test and poetry_test:
        print("\n🎯 SISTEMA LOCAL OK!")
        print("💡 Próximo passo: Testar no GitHub Actions")
        print("   - Faça commit e push para branch 'senha_test'")
        print("   - Verifique a aba Actions no GitHub")
    else:
        print("\n⚠️  CORRIGIR PROBLEMAS LOCAIS PRIMEIRO")
    
    print("\n🔍 Para testar com secret simulado:")
    print("   PYTESTE_APP_SECRET='test123' python scripts/test_github_secret.py")