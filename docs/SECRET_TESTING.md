# 🧪 Teste do GitHub Secret - PYTESTE_APP_SECRET

Este documento explica como testar o sistema de secrets do projeto.

## 📋 Pré-requisitos

1. **GitHub Secret configurado:**
   - Acesse: Repository → Settings → Secrets and variables → Actions
   - Nome: `PYTESTE_APP_SECRET`
   - Valor: Sua chave secreta

2. **Poetry instalado:**
   ```bash
   poetry --version
   ```

## 🏠 Teste Local (Sem Secret)

Execute o teste local para verificar se o sistema está funcionando:

```bash
# Teste 1: Script direto
python scripts/test_local.py

# Teste 2: Via Poetry
poetry run test-local
```

**Resultado esperado:**
- ✅ Script encontrado
- ✅ Poetry funcionando
- ⚠️ GitHub Secret não disponível (esperado)

## 🔧 Teste Local (Com Secret Simulado)

Para testar com um secret simulado:

### Windows (PowerShell):
```powershell
$env:PYTESTE_APP_SECRET="meu-secret-de-teste-123"
python scripts/test_github_secret.py
```

### Linux/Mac:
```bash
PYTESTE_APP_SECRET="meu-secret-de-teste-123" python scripts/test_github_secret.py
```

**Resultado esperado:**
- ✅ PYTESTE_APP_SECRET encontrado
- ✅ Hash SHA256 gerado
- ✅ Arquivo `test_secret_output.py` criado

## 🚀 Teste no GitHub Actions

### Execução Automática:
O teste roda automaticamente quando você:
1. Faz push para `senha_test` ou `main`
2. Cria Pull Request para `main`

### Execução Manual:
1. Acesse: Repository → Actions
2. Selecione: "Test GitHub Secret"
3. Clique: "Run workflow"
4. Escolha branch: `senha_test`
5. Clique: "Run workflow"

### Verificar Resultados:
1. Acesse a aba **Actions**
2. Clique no workflow "Test GitHub Secret"
3. Clique no job "Test PYTESTE_APP_SECRET"
4. Veja os logs:
   - ✅ Setup Python/Poetry
   - ✅ Test GitHub Secret
   - ✅ Check test output
   - ✅ Upload test artifact

## 📄 Arquivos Gerados

### `test_secret_output.py`
Arquivo gerado durante o teste contendo:
- Hash do secret (primeiros 16 chars)
- Timestamp do teste
- Função de verificação

### Logs no GitHub Actions:
```
🧪 Testando GitHub Secret...
==================================================
✅ PYTESTE_APP_SECRET encontrado!
📏 Tamanho: 32 caracteres
🔍 Primeiros 8 chars: meuSecre...
🔍 Últimos 8 chars: ...123456789
🔐 Hash SHA256: a1b2c3d4e5f6...
⏰ Com timestamp: 9z8y7x6w5v4u...
📄 Arquivo de teste criado: test_secret_output.py

🎉 Teste do GitHub Secret: SUCESSO!
```

## 🎯 Próximos Passos

Após todos os testes passarem:

1. **✅ Teste Local OK** → Sistema funciona localmente
2. **✅ Teste GitHub OK** → Secret está configurado corretamente
3. **🚀 Implementar Sistema** → Adicionar auth ao aplicativo

## 🔍 Troubleshooting

### Erro: "PYTESTE_APP_SECRET não encontrado"
- Verifique se o secret está configurado no GitHub
- Nome correto: `PYTESTE_APP_SECRET` (case-sensitive)

### Erro: "Poetry não encontrado"
- Instale Poetry: `pip install poetry`
- Ou use Python direto: `python scripts/test_github_secret.py`

### Teste falha no GitHub Actions:
- Verifique se secret foi criado em Settings → Secrets
- Confirme que está na seção "Actions" (não Environment)

## 📚 Comandos Disponíveis

```bash
# Teste local completo
poetry run test-local

# Teste direto do script
python scripts/test_github_secret.py

# Com secret simulado (PowerShell)
$env:PYTESTE_APP_SECRET="test123"; python scripts/test_github_secret.py
```